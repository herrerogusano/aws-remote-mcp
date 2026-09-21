[CmdletBinding()]
param(
    [string]$StackName = "aws-remote-mcp-dev",
    [string]$Region = "eu-west-1",
    [switch]$ValidateExternalWrites,
    [switch]$ValidateTelegramWrite,
    [switch]$ValidateTrelloWrite,
    [switch]$ValidateCostExplorer,
    [string]$CostStartDate = "",
    [string]$CostEndDate = "",
    [string]$ResourceQuery = "service:lambda region:eu-west-1",
    [ValidateRange(1, 5)][int]$ResourceLimit = 5,
    [switch]$IncludeResourceDetails,
    [switch]$IncludeProjectInventoryDetails,
    [string]$TelegramMessage = "AWS Remote MCP DEV validation successful.",
    [string]$TrelloTitle = "AWS Remote MCP — DEV validation",
    [string]$TrelloDescription = (
        "Disposable validation card created by the closed DEV integration test."
    )
)

$ErrorActionPreference = "Stop"
$validateTelegram = $ValidateExternalWrites -or $ValidateTelegramWrite
$validateTrello = $ValidateExternalWrites -or $ValidateTrelloWrite

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
$functionConfig = Invoke-AwsCli @(
    "lambda", "get-function-configuration",
    "--function-name", $functionName,
    "--region", $Region,
    "--output", "json"
) | ConvertFrom-Json
$issuer = $functionConfig.Environment.Variables.OAUTH_ISSUER
$audience = $functionConfig.Environment.Variables.MCP_RESOURCE_URL
$requiredScope = $functionConfig.Environment.Variables.MCP_REQUIRED_SCOPE
$externalIntegrationsEnabled = `
    $functionConfig.Environment.Variables.EXTERNAL_INTEGRATIONS_ENABLED -eq "true"
$costExplorerEnabled = `
    $functionConfig.Environment.Variables.COST_EXPLORER_ENABLED -eq "true"
if (
    [string]::IsNullOrWhiteSpace($issuer) -or
    [string]::IsNullOrWhiteSpace($requiredScope) -or
    $audience -ne "https://$apiId.execute-api.$Region.amazonaws.com/mcp"
) {
    throw "Deployed Lambda authorization configuration is missing or unexpected."
}

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
            authorizer  = [ordered]@{
                jwt = [ordered]@{
                    claims = [ordered]@{
                        iss       = $issuer
                        aud       = $audience
                        sub       = "direct-synthetic-validation"
                        scope     = $requiredScope
                        token_use = "access"
                    }
                    scopes = @($requiredScope)
                }
            }
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
    $expectedToolNames = @(
        "buscar_recursos_aws",
        "diagnostico",
        "listar_inventario_aws",
        "listar_recursos_proyecto_aws"
    )
    if ($externalIntegrationsEnabled) {
        $expectedToolNames += @(
            "crear_tarjeta_trello",
            "enviar_mensaje_telegram",
            "preparar_mensaje_telegram",
            "preparar_tarjeta_trello"
        )
    }
    if ($costExplorerEnabled) {
        $expectedToolNames += @(
            "consultar_costes_aws",
            "preparar_consulta_costes_aws"
        )
    }
    $expectedToolNames = @($expectedToolNames | Sort-Object)
    if (($toolNames -join ",") -ne ($expectedToolNames -join ",")) {
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

    $inventory = Invoke-DirectMcp `
        -Method "tools/call" `
        -Params @{ name = "listar_inventario_aws"; arguments = @{} } `
        -Name "listar_inventario_aws"
    $inventoryContent = $inventory.result.structuredContent
    if (
        $inventoryContent.status -ne "ok" -or
        $inventoryContent.data.read_only -ne $true -or
        $inventoryContent.data.max_resources_per_service -ne 10 -or
        $inventoryContent.counters.sdk_requests -ne 2 -or
        $inventoryContent.counters.resources -gt 20 -or
        $inventoryContent.counters.external_writes_attempted -ne 0 -or
        $inventoryContent.counters.external_writes_succeeded -ne 0
    ) {
        throw "Bounded AWS inventory contract failed."
    }
    $validation["aws_inventory"] = "ok; 2 reads; max 20 resources; no writes"

    $projectInventory = Invoke-DirectMcp `
        -Method "tools/call" `
        -Params @{ name = "listar_recursos_proyecto_aws"; arguments = @{} } `
        -Name "listar_recursos_proyecto_aws"
    $projectInventoryContent = $projectInventory.result.structuredContent
    if (
        $projectInventoryContent.status -ne "ok" -or
        $projectInventoryContent.data.read_only -ne $true -or
        $projectInventoryContent.data.complete -ne $true -or
        @($projectInventoryContent.data.stacks).Count -ne 4 -or
        $projectInventoryContent.data.total -lt 1 -or
        $projectInventoryContent.data.total -gt 100 -or
        $projectInventoryContent.data.sdk_requests -lt 4 -or
        $projectInventoryContent.data.sdk_requests -gt 80 -or
        $projectInventoryContent.data.writes -ne 0 -or
        $projectInventoryContent.data.external_writes -ne 0 -or
        $projectInventoryContent.counters.sdk_requests -ne `
            $projectInventoryContent.data.sdk_requests -or
        $projectInventoryContent.counters.resources -ne `
            $projectInventoryContent.data.total -or
        $projectInventoryContent.counters.external_writes_attempted -ne 0 -or
        $projectInventoryContent.counters.external_writes_succeeded -ne 0
    ) {
        throw "Complete project inventory contract failed."
    }
    $validation["project_inventory"] = `
        "ok; complete; $($projectInventoryContent.data.total) resources; no writes"
    if ($IncludeProjectInventoryDetails) {
        $validation["project_inventory_resources"] = @(
            $projectInventoryContent.data.resources
        )
    }

    $resourceSearch = Invoke-DirectMcp `
        -Method "tools/call" `
        -Params @{
            name = "buscar_recursos_aws"
            arguments = @{
                query = $ResourceQuery
                limit = $ResourceLimit
            }
        } `
        -Name "buscar_recursos_aws"
    $resourceSearchContent = $resourceSearch.result.structuredContent
    $resourceSearchWarningCodes = @(
        $resourceSearchContent.warnings | ForEach-Object { $_.code }
    )
    $unexpectedSearchWarnings = @(
        $resourceSearchWarningCodes | Where-Object {
            $_ -ne "resource_explorer_invalid_resources"
        }
    )
    if (
        @("ok", "partial") -notcontains $resourceSearchContent.status -or
        (
            $resourceSearchContent.status -eq "ok" -and
            $resourceSearchWarningCodes.Count -ne 0
        ) -or
        (
            $resourceSearchContent.status -eq "partial" -and
            $resourceSearchWarningCodes.Count -eq 0
        ) -or
        $unexpectedSearchWarnings.Count -gt 0 -or
        $resourceSearchContent.data.read_only -ne $true -or
        $resourceSearchContent.data.region -ne "eu-west-1" -or
        $resourceSearchContent.data.returned -lt 1 -or
        $resourceSearchContent.data.returned -gt $ResourceLimit -or
        $resourceSearchContent.counters.sdk_requests -ne 1 -or
        $resourceSearchContent.counters.external_writes_attempted -ne 0 -or
        $resourceSearchContent.counters.external_writes_succeeded -ne 0
    ) {
        throw "Bounded Resource Explorer search contract failed."
    }
    $validation["resource_explorer"] = `
        "$($resourceSearchContent.status); 1 read; max $ResourceLimit resources; no writes"
    if ($IncludeResourceDetails) {
        $validation["resource_explorer_resources"] = @(
            $resourceSearchContent.data.resources
        )
    }

    if ($ValidateCostExplorer) {
        if (-not $costExplorerEnabled) {
            throw "Cost Explorer validation requires the deployed opt-in."
        }
        if (
            $CostStartDate -notmatch '^\d{4}-\d{2}-\d{2}$' -or
            $CostEndDate -notmatch '^\d{4}-\d{2}-\d{2}$'
        ) {
            throw "Cost Explorer validation requires exact start and end dates."
        }

        $costArguments = @{
            start_date = $CostStartDate
            end_date = $CostEndDate
            granularity = "MONTHLY"
            group_by = "SERVICE"
        }
        $costPrepared = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "preparar_consulta_costes_aws"
                arguments = $costArguments
            } `
            -Name "preparar_consulta_costes_aws"
        $costPreview = $costPrepared.result.structuredContent
        if (
            $costPreview.status -ne "confirmation_required" -or
            -not $costPreview.confirmation.token -or
            $costPreview.data.preview.max_cost_usd -ne "0.01" -or
            $costPreview.data.preview.max_api_requests -ne 1 -or
            $costPreview.data.preview.monthly_request_limit -ne 3 -or
            $costPreview.data.preview.monthly_max_api_cost_usd -ne "0.03"
        ) {
            throw "Cost Explorer confirmation preparation failed."
        }

        $costArguments["confirmation"] = $costPreview.confirmation.token
        $costExecuted = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "consultar_costes_aws"
                arguments = $costArguments
            } `
            -Name "consultar_costes_aws"
        $costResult = $costExecuted.result.structuredContent
        if (
            $costResult.status -ne "ok" -or
            $costResult.data.read_only -ne $true -or
            $costResult.data.max_cost_usd -ne "0.01" -or
            $costResult.data.monthly_request_limit -ne 3 -or
            $costResult.data.monthly_max_api_cost_usd -ne "0.03" -or
            $costResult.data.returned_periods -gt 1 -or
            $costResult.data.returned_groups -lt 1 -or
            $costResult.data.returned_groups -gt 100 -or
            $costResult.counters.sdk_requests -ne 1 -or
            $costResult.counters.external_writes_attempted -ne 0 -or
            $costResult.counters.external_writes_succeeded -ne 0
        ) {
            throw "Confirmed Cost Explorer query contract failed."
        }
        $validation["cost_explorer"] = `
            "ok; 1 paid read; max USD 0.01; monthly cap USD 0.03; no writes"
    }

    if (($validateTelegram -or $validateTrello) -and -not $externalIntegrationsEnabled) {
        throw "External write validation requires the deployed integration profile."
    }

    if ($validateTelegram) {
        $telegramArguments = @{
            destination = "owner"
            message = $TelegramMessage
        }
        $telegramPrepared = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "preparar_mensaje_telegram"
                arguments = $telegramArguments
            } `
            -Name "preparar_mensaje_telegram"
        $telegramPreview = $telegramPrepared.result.structuredContent
        if (
            $telegramPreview.status -ne "confirmation_required" -or
            -not $telegramPreview.confirmation.token
        ) {
            throw "Telegram confirmation preparation failed."
        }
        $telegramArguments["confirmation"] = $telegramPreview.confirmation.token
        $telegramExecuted = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "enviar_mensaje_telegram"
                arguments = $telegramArguments
            } `
            -Name "enviar_mensaje_telegram"
        $telegramResult = $telegramExecuted.result.structuredContent
        if (
            $telegramResult.status -ne "ok" -or
            $telegramResult.counters.external_writes_attempted -ne 1 -or
            $telegramResult.counters.external_writes_succeeded -ne 1
        ) {
            throw "Telegram validation write was not confirmed."
        }
        $validation["telegram"] = "ok; one confirmed write"
    }

    if ($validateTrello) {
        $trelloArguments = @{
            board = "portfolio"
            list_name = "inbox"
            title = $TrelloTitle
            description = $TrelloDescription
        }
        $trelloPrepared = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "preparar_tarjeta_trello"
                arguments = $trelloArguments
            } `
            -Name "preparar_tarjeta_trello"
        $trelloPreview = $trelloPrepared.result.structuredContent
        if (
            $trelloPreview.status -ne "confirmation_required" -or
            -not $trelloPreview.confirmation.token
        ) {
            throw "Trello confirmation preparation failed."
        }
        $trelloArguments["confirmation"] = $trelloPreview.confirmation.token
        $trelloExecuted = Invoke-DirectMcp `
            -Method "tools/call" `
            -Params @{
                name = "crear_tarjeta_trello"
                arguments = $trelloArguments
            } `
            -Name "crear_tarjeta_trello"
        $trelloResult = $trelloExecuted.result.structuredContent
        if (
            $trelloResult.status -ne "ok" -or
            $trelloResult.counters.external_writes_attempted -ne 1 -or
            $trelloResult.counters.external_writes_succeeded -ne 1
        ) {
            throw "Trello validation write was not confirmed."
        }
        $validation["trello"] = "ok; one confirmed write"
    }
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
