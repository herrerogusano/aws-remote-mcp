[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$WindowMinutes = 5,
    [ValidateRange(1, 20)]
    [int]$RequestThreshold = 20,
    [ValidateSet(1)]
    [int]$ReservedConcurrency = 1,
    [string]$StackName = "aws-remote-mcp-dev",
    [string]$AuthStackName = "aws-remote-mcp-auth-dev",
    [string]$Username = "portfolio-admin",
    [ValidateSet("Cognito", "ExternalOAuth")]
    [string]$AuthorizationProfile = "Cognito",
    [string]$AuthorizationServer = "",
    [string]$RequiredScope = "",
    [switch]$UseUnreservedConcurrency,
    [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"
$alarmName = "aws-remote-mcp-dev-request-kill-switch"

function Invoke-AwsCli {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $result = & aws @Arguments 2> $stderrPath
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $operation = @($Arguments | Select-Object -First 2) -join " "
            throw "AWS CLI failed during allowlisted operation: $operation"
        }
        return $result
    }
    finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
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
$stageName = Get-StackOutput "DevStageName"
$endpoint = Get-StackOutput "DevMcpEndpoint"
$expectedScope = if ($AuthorizationProfile -eq "Cognito") {
    "$endpoint/use"
}
else {
    $RequiredScope
}
if ([string]::IsNullOrWhiteSpace($expectedScope)) {
    throw "External OAuth requires an explicit scope"
}
$functionName = Get-StackOutput "DevFunctionName"
$shutdownArn = Get-StackOutput "SafetyShutdownFunctionArn"
$schedulerRoleArn = Get-StackOutput "SafetyShutdownSchedulerRoleArn"
$scheduleGroup = Get-StackOutput "SafetyShutdownScheduleGroupName"
$topicArn = Get-StackOutput "SafetyShutdownTopicArn"

$api = Invoke-AwsCli @(
    "apigatewayv2", "get-api", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$concurrency = Invoke-AwsCli @(
    "lambda", "get-function-concurrency", "--function-name", $functionName,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$routes = Invoke-AwsCli @(
    "apigatewayv2", "get-routes", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$mcpRoute = $routes.Items | Where-Object RouteKey -eq "POST /mcp"
$authorizers = Invoke-AwsCli @(
    "apigatewayv2", "get-authorizers", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$jwtAuthorizer = $authorizers.Items | Where-Object AuthorizerId -eq $mcpRoute.AuthorizerId
$stages = Invoke-AwsCli @(
    "apigatewayv2", "get-stages", "--api-id", $apiId,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$expectedRoutes = @(
    "GET /.well-known/oauth-protected-resource/mcp",
    "OPTIONS /.well-known/oauth-protected-resource/mcp",
    "POST /mcp"
)
if (
    -not $api.DisableExecuteApiEndpoint -or
    $concurrency.ReservedConcurrentExecutions -ne 0 -or
    @($mcpRoute).Count -ne 1 -or
    $mcpRoute.AuthorizationType -ne "JWT" -or
    @($mcpRoute.AuthorizationScopes).Count -ne 1 -or
    $mcpRoute.AuthorizationScopes[0] -ne $expectedScope -or
    (@($routes.Items.RouteKey | Sort-Object) -join "|") -ne ($expectedRoutes -join "|") -or
    @($stages.Items).Count -ne 1 -or
    $stageName -ne '$default' -or
    $stages.Items[0].StageName -ne $stageName -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingRateLimit -ne 1 -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingBurstLimit -ne 1
) {
    throw "Refusing to open from an unexpected API, compute or JWT state"
}

if ($AuthorizationProfile -eq "Cognito") {
    $auth = Invoke-AwsCli @(
        "cloudformation", "describe-stacks", "--stack-name", $AuthStackName,
        "--region", $Region, "--output", "json"
    ) | ConvertFrom-Json
    $authOutputs = $auth.Stacks[0].Outputs
    $poolId = ($authOutputs | Where-Object OutputKey -eq "UserPoolId").OutputValue
    $clientId = ($authOutputs | Where-Object OutputKey -eq "InspectorClientId").OutputValue
    $issuer = ($authOutputs | Where-Object OutputKey -eq "Issuer").OutputValue
    $requiredScope = ($authOutputs | Where-Object OutputKey -eq "RequiredScope").OutputValue
    $gate = ($authOutputs | Where-Object OutputKey -eq "TotpEnrollmentGate").OutputValue
    $client = Invoke-AwsCli @(
        "cognito-idp", "describe-user-pool-client", "--user-pool-id", $poolId,
        "--client-id", $clientId, "--region", $Region, "--output", "json"
    ) | ConvertFrom-Json
    $user = Invoke-AwsCli @(
        "cognito-idp", "admin-get-user", "--user-pool-id", $poolId,
        "--username", $Username, "--region", $Region, "--output", "json"
    ) | ConvertFrom-Json
    if (
        $gate -ne "false" -or
        $requiredScope -ne $expectedScope -or
        @($client.UserPoolClient.AllowedOAuthScopes).Count -ne 1 -or
        $client.UserPoolClient.AllowedOAuthScopes[0] -ne $expectedScope -or
        $user.UserStatus -ne "CONFIRMED" -or
        @($user.UserMFASettingList) -notcontains "SOFTWARE_TOKEN_MFA"
    ) {
        throw "Refusing to open without the exact closed Cognito and TOTP state"
    }
}
else {
    if ([string]::IsNullOrWhiteSpace($AuthorizationServer)) {
        throw "External OAuth requires an authorization-server URL"
    }
    $issuer = $AuthorizationServer.TrimEnd('/')
    & "$PSScriptRoot\validate-oauth-provider.ps1" `
        -AuthorizationServer $issuer `
        -Resource $endpoint `
        -RequiredScope $expectedScope | Out-Null
}

if (
    @($jwtAuthorizer).Count -ne 1 -or
    $jwtAuthorizer.AuthorizerType -ne "JWT" -or
    $jwtAuthorizer.JwtConfiguration.Issuer.TrimEnd('/') -ne $issuer.TrimEnd('/') -or
    @($jwtAuthorizer.JwtConfiguration.Audience).Count -ne 1 -or
    $jwtAuthorizer.JwtConfiguration.Audience[0] -ne $endpoint
) {
    throw "Refusing to open without the exact OAuth issuer and resource audience"
}

$existingAlarms = Invoke-AwsCli @(
    "cloudwatch", "describe-alarms", "--alarm-names", $alarmName,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$existingSchedules = Invoke-AwsCli @(
    "scheduler", "list-schedules", "--group-name", $scheduleGroup,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
if (
    @($existingAlarms.MetricAlarms).Count -ne 0 -or
    @($existingSchedules.Schedules).Count -ne 0
) {
    throw "Refusing to overlap or overwrite an existing validation window"
}

if ($UseUnreservedConcurrency) {
    if ($RequestThreshold -gt 15) {
        throw "Unreserved fallback requires a request tripwire of 15 or lower"
    }
    $quota = Invoke-AwsCli @(
        "service-quotas", "get-service-quota",
        "--service-code", "lambda",
        "--quota-code", "L-B99A9384",
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
    $accountSettings = Invoke-AwsCli @(
        "lambda", "get-account-settings",
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
    if (
        $quota.Quota.Value -ne 10 -or
        $accountSettings.AccountLimit.ConcurrentExecutions -ne 10 -or
        $accountSettings.AccountLimit.UnreservedConcurrentExecutions -ne 10
    ) {
        throw "Unreserved fallback requires the reviewed regional concurrency cap of 10"
    }
}
else {
    # Lambda must retain at least one hundred unreserved executions after applying
    # this function's reservation. Other reservations are already reflected in
    # UnreservedConcurrentExecutions. The shutdown function uses that shared pool,
    # so operational review must also account for concurrent unreserved workloads.
    $quota = Invoke-AwsCli @(
        "service-quotas", "get-service-quota",
        "--service-code", "lambda",
        "--quota-code", "L-B99A9384",
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
    $accountSettings = Invoke-AwsCli @(
        "lambda", "get-account-settings",
        "--region", $Region,
        "--output", "json"
    ) | ConvertFrom-Json
    $minimumRegionalCapacity = 100 + $ReservedConcurrency
    if (
        $quota.Quota.Value -lt $minimumRegionalCapacity -or
        $accountSettings.AccountLimit.ConcurrentExecutions -lt $minimumRegionalCapacity -or
        $accountSettings.AccountLimit.UnreservedConcurrentExecutions -lt $minimumRegionalCapacity
    ) {
        throw "Reserved concurrency requires verified regional and unreserved capacity of at least $minimumRegionalCapacity"
    }
}

$closeAt = [DateTime]::UtcNow.AddMinutes($WindowMinutes)
$scheduleName = "aws-remote-mcp-dev-auto-close-$($closeAt.ToString('yyyyMMddHHmmss'))"
$target = "Arn=$shutdownArn,RoleArn=$schedulerRoleArn,Input='{}'"

try {
    # Install independent AWS-side closure before either execution surface opens.
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

    # A request-volume tripwire closes the window before the scheduled deadline.
    Invoke-AwsCli @(
        "cloudwatch", "put-metric-alarm",
        "--alarm-name", $alarmName,
        "--region", $Region,
        "--namespace", "AWS/ApiGateway",
        "--metric-name", "Count",
        "--dimensions", "Name=ApiId,Value=$apiId", "Name=Stage,Value=$stageName",
        "--statistic", "Sum",
        "--period", "60",
        "--evaluation-periods", "1",
        "--datapoints-to-alarm", "1",
        "--threshold", "$RequestThreshold",
        "--comparison-operator", "GreaterThanOrEqualToThreshold",
        "--treat-missing-data", "notBreaching",
        "--alarm-actions", $topicArn
    ) | Out-Null

    if ($UseUnreservedConcurrency) {
        Invoke-AwsCli @(
            "lambda", "delete-function-concurrency",
            "--function-name", $functionName,
            "--region", $Region
        ) | Out-Null
    }
    else {
        Invoke-AwsCli @(
            "lambda", "put-function-concurrency",
            "--function-name", $functionName,
            "--reserved-concurrent-executions", "$ReservedConcurrency",
            "--region", $Region
        ) | Out-Null
    }
    Invoke-AwsCli @(
        "apigatewayv2", "update-api",
        "--api-id", $apiId,
        "--no-disable-execute-api-endpoint",
        "--region", $Region
    ) | Out-Null
    $openedApi = Invoke-AwsCli @(
        "apigatewayv2", "get-api", "--api-id", $apiId,
        "--region", $Region, "--output", "json"
    ) | ConvertFrom-Json
    $openedConcurrency = Invoke-AwsCli @(
        "lambda", "get-function-concurrency", "--function-name", $functionName,
        "--region", $Region, "--output", "json"
    ) | ConvertFrom-Json
    $unexpectedConcurrency = if ($UseUnreservedConcurrency) {
        $null -ne $openedConcurrency.ReservedConcurrentExecutions
    }
    else {
        $openedConcurrency.ReservedConcurrentExecutions -ne $ReservedConcurrency
    }
    if ($openedApi.DisableExecuteApiEndpoint -or $unexpectedConcurrency) {
        throw "The bounded window did not reach its exact open state"
    }
}
catch {
    $openingFailure = $_
    $cleanupFailures = [Collections.Generic.List[string]]::new()
    try {
        Invoke-AwsCli @(
            "apigatewayv2", "update-api", "--api-id", $apiId,
            "--disable-execute-api-endpoint", "--region", $Region
        ) | Out-Null
    }
    catch { }
    try {
        Invoke-AwsCli @(
            "lambda", "put-function-concurrency", "--function-name", $functionName,
            "--reserved-concurrent-executions", "0", "--region", $Region
        ) | Out-Null
    }
    catch { }
    try {
        $closedApi = Invoke-AwsCli @(
            "apigatewayv2", "get-api", "--api-id", $apiId,
            "--region", $Region, "--output", "json"
        ) | ConvertFrom-Json
        if (-not $closedApi.DisableExecuteApiEndpoint) {
            $cleanupFailures.Add("disable_api")
        }
    }
    catch { $cleanupFailures.Add("verify_api_disabled") }
    try {
        $stoppedConcurrency = Invoke-AwsCli @(
            "lambda", "get-function-concurrency", "--function-name", $functionName,
            "--region", $Region, "--output", "json"
        ) | ConvertFrom-Json
        if ($stoppedConcurrency.ReservedConcurrentExecutions -ne 0) {
            $cleanupFailures.Add("stop_lambda")
        }
    }
    catch { $cleanupFailures.Add("verify_lambda_stopped") }
    # Delete both deterministic controls even when their create response was
    # ambiguous. Verification below distinguishes absence from cleanup failure.
    try {
        Invoke-AwsCli @(
            "cloudwatch", "delete-alarms", "--alarm-names", $alarmName,
            "--region", $Region
        ) | Out-Null
    }
    catch { }
    try {
        Invoke-AwsCli @(
            "scheduler", "delete-schedule", "--name", $scheduleName,
            "--group-name", $scheduleGroup, "--region", $Region
        ) | Out-Null
    }
    catch { }
    try {
        $remainingAlarm = Invoke-AwsCli @(
            "cloudwatch", "describe-alarms", "--alarm-names", $alarmName,
            "--region", $Region, "--output", "json"
        ) | ConvertFrom-Json
        if (@($remainingAlarm.MetricAlarms).Count -ne 0) {
            $cleanupFailures.Add("delete_traffic_alarm")
        }
    }
    catch { $cleanupFailures.Add("verify_traffic_alarm_absent") }
    try {
        $remainingSchedules = Invoke-AwsCli @(
            "scheduler", "list-schedules", "--group-name", $scheduleGroup,
            "--region", $Region, "--output", "json"
        ) | ConvertFrom-Json
        if (@($remainingSchedules.Schedules | Where-Object Name -eq $scheduleName).Count -ne 0) {
            $cleanupFailures.Add("delete_auto_close_schedule")
        }
    }
    catch { $cleanupFailures.Add("verify_auto_close_schedule_absent") }
    if ($cleanupFailures.Count -gt 0) {
        throw "Window opening failed ($openingFailure); fail-closed rollback needs attention: $($cleanupFailures -join ', ')"
    }
    throw $openingFailure
}

[pscustomobject]@{
    OpenedAtUtc       = [DateTime]::UtcNow.ToString("O")
    AutomaticCloseUtc = $closeAt.ToString("O")
    RequestTripwire   = $RequestThreshold
    Authentication    = "$AuthorizationProfile JWT with $expectedScope"
    ConcurrencyMode   = if ($UseUnreservedConcurrency) { "unreserved-account-cap-10" } else { "reserved-$ReservedConcurrency" }
    ScheduleName      = $scheduleName
}
