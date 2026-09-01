[CmdletBinding()]
param(
    [ValidateSet("eu-west-1")]
    [string]$Region = "eu-west-1",
    [string]$AppStack = "aws-remote-mcp-dev",
    [string]$AuthStack = "aws-remote-mcp-auth-dev",
    [string]$Username = "portfolio-admin"
)

$ErrorActionPreference = "Stop"
$inspectorPackage = "@modelcontextprotocol/inspector@2.4.0"
$openScript = Join-Path $PSScriptRoot "open-dev-window.ps1"
$closeScript = Join-Path $PSScriptRoot "close-dev-window.ps1"

foreach ($requiredPath in @($openScript, $closeScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file not found: $requiredPath"
    }
}

function Invoke-AwsJson {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $result = & aws @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI control-plane read failed"
    }
    return $result | ConvertFrom-Json
}

$app = Invoke-AwsJson @(
    "cloudformation", "describe-stacks", "--stack-name", $AppStack,
    "--region", $Region, "--output", "json"
)
$auth = Invoke-AwsJson @(
    "cloudformation", "describe-stacks", "--stack-name", $AuthStack,
    "--region", $Region, "--output", "json"
)
$appOutputs = $app.Stacks[0].Outputs
$authOutputs = $auth.Stacks[0].Outputs
$apiId = ($appOutputs | Where-Object OutputKey -eq "DevApiId").OutputValue
$functionName = ($appOutputs | Where-Object OutputKey -eq "DevFunctionName").OutputValue
$endpoint = ($appOutputs | Where-Object OutputKey -eq "DevMcpEndpoint").OutputValue
$poolId = ($authOutputs | Where-Object OutputKey -eq "UserPoolId").OutputValue
$clientId = ($authOutputs | Where-Object OutputKey -eq "InspectorClientId").OutputValue
$issuer = ($authOutputs | Where-Object OutputKey -eq "Issuer").OutputValue
$gate = ($authOutputs | Where-Object OutputKey -eq "TotpEnrollmentGate").OutputValue
$scheduleGroup = ($appOutputs | Where-Object OutputKey -eq "SafetyShutdownScheduleGroupName").OutputValue

if ($endpoint -ne "https://$apiId.execute-api.$Region.amazonaws.com/mcp") {
    throw "Unexpected MCP endpoint"
}
if ($gate -ne "false") {
    throw "TOTP enrollment scope must be closed before validation"
}
if (
    $app.Stacks[0].StackStatus -notin @("CREATE_COMPLETE", "UPDATE_COMPLETE") -or
    $auth.Stacks[0].StackStatus -notin @("CREATE_COMPLETE", "UPDATE_COMPLETE")
) {
    throw "Both CloudFormation stacks must be complete"
}

$api = Invoke-AwsJson @(
    "apigatewayv2", "get-api", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
)
$concurrency = Invoke-AwsJson @(
    "lambda", "get-function-concurrency", "--function-name", $functionName,
    "--region", $Region, "--output", "json"
)
$routes = Invoke-AwsJson @(
    "apigatewayv2", "get-routes", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
)
$mcpRoute = $routes.Items | Where-Object RouteKey -eq "POST /mcp"
$authorizers = Invoke-AwsJson @(
    "apigatewayv2", "get-authorizers", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
)
$jwtAuthorizer = $authorizers.Items | Where-Object AuthorizerId -eq $mcpRoute.AuthorizerId
$stages = Invoke-AwsJson @(
    "apigatewayv2", "get-stages", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
)
$expectedRoutes = @(
    "GET /.well-known/oauth-protected-resource/mcp",
    "OPTIONS /.well-known/oauth-protected-resource/mcp",
    "POST /mcp"
)
if (-not $api.DisableExecuteApiEndpoint -or $concurrency.ReservedConcurrentExecutions -ne 0) {
    throw "Validation must start with the endpoint and compute closed"
}
if ((@($routes.Items.RouteKey | Sort-Object) -join "|") -ne ($expectedRoutes -join "|")) {
    throw "The API has unexpected routes"
}
if (
    @($mcpRoute).Count -ne 1 -or
    $mcpRoute.AuthorizationType -ne "JWT" -or
    @($mcpRoute.AuthorizationScopes).Count -ne 1 -or
    $mcpRoute.AuthorizationScopes[0] -ne "aws-remote-mcp/use"
) {
    throw "The MCP route does not have the exact JWT authorization contract"
}
if (
    @($jwtAuthorizer).Count -ne 1 -or
    $jwtAuthorizer.AuthorizerType -ne "JWT" -or
    @($jwtAuthorizer.IdentitySource).Count -ne 1 -or
    $jwtAuthorizer.IdentitySource[0] -ne '$request.header.Authorization' -or
    $jwtAuthorizer.JwtConfiguration.Issuer -ne $issuer -or
    @($jwtAuthorizer.JwtConfiguration.Audience).Count -ne 1 -or
    $jwtAuthorizer.JwtConfiguration.Audience[0] -ne $endpoint
) {
    throw "The JWT authorizer does not match the exact Cognito contract"
}
if (
    @($stages.Items).Count -ne 1 -or
    $stages.Items[0].StageName -ne '$default' -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingRateLimit -ne 1 -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingBurstLimit -ne 1
) {
    throw "The API stage or throttle has drifted"
}

$client = Invoke-AwsJson @(
    "cognito-idp", "describe-user-pool-client", "--user-pool-id", $poolId,
    "--client-id", $clientId, "--region", $Region, "--output", "json"
)
if (
    @($client.UserPoolClient.AllowedOAuthScopes).Count -ne 1 -or
    $client.UserPoolClient.AllowedOAuthScopes[0] -ne "aws-remote-mcp/use"
) {
    throw "The Inspector client has unexpected OAuth scopes"
}

$user = Invoke-AwsJson @(
    "cognito-idp", "admin-get-user", "--user-pool-id", $poolId,
    "--username", $Username, "--region", $Region, "--output", "json"
)
$users = Invoke-AwsJson @(
    "cognito-idp", "list-users", "--user-pool-id", $poolId,
    "--limit", "2", "--region", $Region, "--output", "json"
)
if (
    $user.UserStatus -ne "CONFIRMED" -or
    @($user.UserMFASettingList) -notcontains "SOFTWARE_TOKEN_MFA"
) {
    throw "Complete the validation identity's TOTP enrollment first"
}
if (@($users.Users).Count -ne 1 -or $users.Users[0].Username -ne $Username) {
    throw "Validation requires exactly the expected identity"
}

$alarms = Invoke-AwsJson @(
    "cloudwatch", "describe-alarms", "--alarm-names",
    "aws-remote-mcp-dev-request-kill-switch", "--region", $Region, "--output", "json"
)
$schedules = Invoke-AwsJson @(
    "scheduler", "list-schedules", "--group-name", $scheduleGroup,
    "--region", $Region, "--output", "json"
)
if (@($alarms.MetricAlarms).Count -ne 0 -or @($schedules.Schedules).Count -ne 0) {
    throw "Temporary validation controls from an earlier window still exist"
}

# Download and resolve the pinned Inspector before the AWS validation window opens.
& npx --yes $inspectorPackage --cli --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "The pinned MCP Inspector could not be prepared"
}

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$storageDir = Join-Path $tempRoot ("aws-remote-mcp-oauth-" + [guid]::NewGuid().ToString("N"))
$resolvedStorage = [IO.Path]::GetFullPath($storageDir)
if (-not $resolvedStorage.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create OAuth state outside the system temporary directory"
}
New-Item -ItemType Directory -Path $resolvedStorage | Out-Null

$previousStorage = $env:MCP_STORAGE_DIR
$previousAutoOpen = $env:MCP_AUTO_OPEN_ENABLED
$cleanupFailures = [Collections.Generic.List[string]]::new()
try {
    $env:MCP_STORAGE_DIR = $resolvedStorage
    $env:MCP_AUTO_OPEN_ENABLED = "true"
    & $openScript -WindowMinutes 5 -RequestThreshold 15 -StackName $AppStack -Region $Region

    & npx --offline --yes $inspectorPackage --cli `
        --server-url $endpoint --transport http `
        --client-id $clientId `
        --callback-url http://127.0.0.1:6276/oauth/callback `
        --method tools/list --strict --format json
    if ($LASTEXITCODE -ne 0) { throw "Inspector tool discovery failed" }

    foreach ($toolName in @("diagnostico", "listar_recursos_aws_sintetico")) {
        & npx --offline --yes $inspectorPackage --cli `
            --server-url $endpoint --transport http `
            --client-id $clientId --stored-auth-only `
            --method tools/call --tool-name $toolName --format json
        if ($LASTEXITCODE -ne 0) { throw "Inspector call failed: $toolName" }
    }
}
finally {
    try { & $closeScript -StackName $AppStack -Region $Region } catch {
        $cleanupFailures.Add("close_aws_window")
    }
    $env:MCP_STORAGE_DIR = $previousStorage
    $env:MCP_AUTO_OPEN_ENABLED = $previousAutoOpen
    try {
        if (Test-Path -LiteralPath $resolvedStorage) {
            Remove-Item -LiteralPath $resolvedStorage -Recurse -Force
        }
    }
    catch { $cleanupFailures.Add("delete_temporary_oauth_state") }
    if ($cleanupFailures.Count -gt 0) {
        throw "Validation cleanup needs attention: $($cleanupFailures -join ', ')"
    }
}

Write-Output "Bounded Inspector validation completed and all temporary state was closed."
