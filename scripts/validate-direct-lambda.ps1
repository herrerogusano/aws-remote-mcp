[CmdletBinding()]
param(
    [string]$StackName = "aws-remote-mcp-dev",
    [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"

function Invoke-AwsCli {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $result = & aws @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI command failed."
    }
    return $result
}

function Get-StackOutput {
    param([Parameter(Mandatory)][string]$OutputKey)

    $query = "Stacks[0].Outputs[?OutputKey=='$OutputKey'].OutputValue | [0]"
    $value = Invoke-AwsCli @(
        "cloudformation", "describe-stacks",
        "--stack-name", $StackName,
        "--region", $Region,
        "--query", $query,
        "--output", "text"
    )
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq "None") {
        throw "Missing stack output: $OutputKey"
    }
    return "$value".Trim()
}

$apiId = Get-StackOutput "DevApiId"
$functionName = Get-StackOutput "DevFunctionName"
$shutdownArn = Get-StackOutput "SafetyShutdownFunctionArn"
$schedulerRoleArn = Get-StackOutput "SafetyShutdownSchedulerRoleArn"
$scheduleGroup = Get-StackOutput "SafetyShutdownScheduleGroupName"

$endpointDisabled = Invoke-AwsCli @(
    "apigatewayv2", "get-api",
    "--api-id", $apiId,
    "--region", $Region,
    "--query", "DisableExecuteApiEndpoint",
    "--output", "text"
)
if ("$endpointDisabled".Trim() -ne "True") {
    throw "Direct validation requires the API endpoint to remain disabled."
}

$closeAt = [DateTime]::UtcNow.AddMinutes(5)
$scheduleName = "aws-remote-mcp-dev-direct-auto-close-$($closeAt.ToString('yyyyMMddHHmmss'))"
$target = "Arn=$shutdownArn,RoleArn=$schedulerRoleArn,Input='{}'"

# Install an independent AWS-side deadline before allowing direct invocation.
Invoke-AwsCli @(
    "scheduler", "create-schedule",
    "--name", $scheduleName,
    "--group-name", $scheduleGroup,
    "--region", $Region,
    "--schedule-expression", "at($($closeAt.ToString('yyyy-MM-ddTHH:mm:ss')))",
    "--schedule-expression-timezone", "UTC",
    "--flexible-time-window", "Mode=OFF",
    "--target", $target,
    "--action-after-completion", "DELETE"
) | Out-Null

function New-McpEventJson {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][hashtable]$Params,
        [string]$Name = ""
    )

    $headers = [ordered]@{
        accept                 = "application/json"
        "content-type"         = "application/json"
        host                   = "$apiId.execute-api.$Region.amazonaws.com"
        "mcp-protocol-version" = "2026-07-28"
        "mcp-method"           = $Method
    }
    if ($Name) { $headers["mcp-name"] = $Name }

    $requestParams = [ordered]@{}
    foreach ($key in $Params.Keys) { $requestParams[$key] = $Params[$key] }
    $requestParams["_meta"] = [ordered]@{
        "io.modelcontextprotocol/protocolVersion"    = "2026-07-28"
        "io.modelcontextprotocol/clientInfo"         = [ordered]@{
            name    = "direct-lambda-validation"
            version = "1"
        }
        "io.modelcontextprotocol/clientCapabilities" = [ordered]@{}
    }
    $body = [ordered]@{
        jsonrpc = "2.0"
        id      = 1
        method  = $Method
        params  = $requestParams
    } | ConvertTo-Json -Depth 10 -Compress

    return [ordered]@{
        version          = "2.0"
        routeKey         = "POST /mcp"
        rawPath          = "/mcp"
        rawQueryString   = ""
        headers          = $headers
        requestContext   = [ordered]@{
            accountId   = "direct-validation"
            apiId       = $apiId
            domainName  = "$apiId.execute-api.$Region.amazonaws.com"
            domainPrefix = $apiId
            http        = [ordered]@{
                method    = "POST"
                path      = "/mcp"
                protocol  = "HTTP/1.1"
                sourceIp  = "127.0.0.1"
                userAgent = "direct-lambda-validation"
            }
            requestId   = [guid]::NewGuid().ToString("N")
            routeKey    = "POST /mcp"
            stage       = '$default'
            time        = ""
            timeEpoch   = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        }
        body             = $body
        isBase64Encoded  = $false
    } | ConvertTo-Json -Depth 12 -Compress
}

function Invoke-DirectMcp {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][hashtable]$Params,
        [string]$Name = ""
    )

    $eventJson = New-McpEventJson -Method $Method -Params $Params -Name $Name
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($eventJson))
    $responsePath = [IO.Path]::GetTempFileName()
    try {
        $metadata = Invoke-AwsCli @(
            "lambda", "invoke",
            "--function-name", $functionName,
            "--region", $Region,
            "--invocation-type", "RequestResponse",
            "--payload", $payload,
            $responsePath
        ) | ConvertFrom-Json
        if ($metadata.FunctionError) {
            throw "Lambda reported an invocation error for $Method/$Name."
        }

        $response = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
        if ($response.statusCode -ne 200) {
            throw "Unexpected application status for $Method/$Name."
        }
        $responseBody = $response.body | ConvertFrom-Json
        if ($responseBody.error) {
            throw "MCP returned an error for $Method/$Name."
        }
        return $responseBody
    }
    finally {
        if (Test-Path -LiteralPath $responsePath) {
            Remove-Item -LiteralPath $responsePath -Force
        }
    }
}

$validation = [ordered]@{}
$cleanupFailures = [Collections.Generic.List[string]]::new()
try {
    Invoke-AwsCli @(
        "lambda", "delete-function-concurrency",
        "--function-name", $functionName,
        "--region", $Region
    ) | Out-Null

    $listed = Invoke-DirectMcp -Method "tools/list" -Params @{}
    $toolNames = @($listed.result.tools | ForEach-Object { $_.name } | Sort-Object)
    if (($toolNames -join ",") -ne "diagnostico,listar_recursos_aws_sintetico") {
        throw "Unexpected tool list."
    }
    $validation["tools_list"] = $toolNames -join ", "

    $diagnostic = Invoke-DirectMcp `
        -Method "tools/call" `
        -Params @{ name = "diagnostico"; arguments = @{} } `
        -Name "diagnostico"
    $diagnosticContent = $diagnostic.result.structuredContent
    if (
        $diagnosticContent.environment -ne "dev" -or
        $diagnosticContent.external_side_effects -ne $false
    ) {
        throw "Diagnostic safety contract failed."
    }
    $validation["diagnostico"] = "ok; dev; no external side effects"

    $synthetic = Invoke-DirectMcp `
        -Method "tools/call" `
        -Params @{ name = "listar_recursos_aws_sintetico"; arguments = @{} } `
        -Name "listar_recursos_aws_sintetico"
    if ($synthetic.result.structuredContent.status -ne "ok") {
        throw "Synthetic inventory contract failed."
    }
    $validation["synthetic_inventory"] = "ok"
}
finally {
    & aws lambda put-function-concurrency --function-name $functionName --reserved-concurrent-executions 0 --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { $cleanupFailures.Add("stop_lambda") }

    & aws apigatewayv2 update-api --api-id $apiId --disable-execute-api-endpoint --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { $cleanupFailures.Add("disable_api") }

    & aws scheduler delete-schedule --name $scheduleName --group-name $scheduleGroup --region $Region | Out-Null
    if ($LASTEXITCODE -ne 0) { $cleanupFailures.Add("delete_auto_close_schedule") }

    if ($cleanupFailures.Count -gt 0) {
        throw "Direct-validation cleanup needs attention: $($cleanupFailures -join ', ')"
    }
}

$validation | ConvertTo-Json
