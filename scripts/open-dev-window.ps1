[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$WindowMinutes = 5,
    [ValidateRange(1, 20)]
    [int]$RequestThreshold = 20,
    [string]$StackName = "aws-remote-mcp-dev",
    [string]$AuthStackName = "aws-remote-mcp-auth-dev",
    [string]$Username = "portfolio-admin",
    [switch]$UseUnreservedConcurrency,
    [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"
$alarmName = "aws-remote-mcp-dev-request-kill-switch"

function Invoke-AwsCli {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $result = & aws @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI failed: aws $($Arguments -join ' ')"
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
$stageName = Get-StackOutput "DevStageName"
$endpoint = Get-StackOutput "DevMcpEndpoint"
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
    $mcpRoute.AuthorizationScopes[0] -ne "aws-remote-mcp/use" -or
    (@($routes.Items.RouteKey | Sort-Object) -join "|") -ne ($expectedRoutes -join "|") -or
    @($stages.Items).Count -ne 1 -or
    $stageName -ne '$default' -or
    $stages.Items[0].StageName -ne $stageName -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingRateLimit -ne 1 -or
    $stages.Items[0].DefaultRouteSettings.ThrottlingBurstLimit -ne 1
) {
    throw "Refusing to open from an unexpected API, compute or JWT state"
}

$auth = Invoke-AwsCli @(
    "cloudformation", "describe-stacks", "--stack-name", $AuthStackName,
    "--region", $Region, "--output", "json"
) | ConvertFrom-Json
$authOutputs = $auth.Stacks[0].Outputs
$poolId = ($authOutputs | Where-Object OutputKey -eq "UserPoolId").OutputValue
$clientId = ($authOutputs | Where-Object OutputKey -eq "InspectorClientId").OutputValue
$issuer = ($authOutputs | Where-Object OutputKey -eq "Issuer").OutputValue
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
    @($client.UserPoolClient.AllowedOAuthScopes).Count -ne 1 -or
    $client.UserPoolClient.AllowedOAuthScopes[0] -ne "aws-remote-mcp/use" -or
    $user.UserStatus -ne "CONFIRMED" -or
    @($user.UserMFASettingList) -notcontains "SOFTWARE_TOKEN_MFA" -or
    @($jwtAuthorizer).Count -ne 1 -or
    $jwtAuthorizer.AuthorizerType -ne "JWT" -or
    $jwtAuthorizer.JwtConfiguration.Issuer -ne $issuer -or
    @($jwtAuthorizer.JwtConfiguration.Audience).Count -ne 1 -or
    $jwtAuthorizer.JwtConfiguration.Audience[0] -ne $endpoint
) {
    throw "Refusing to open without the exact closed Cognito and TOTP state"
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

$closeAt = [DateTime]::UtcNow.AddMinutes($WindowMinutes)
$scheduleName = "aws-remote-mcp-dev-auto-close-$($closeAt.ToString('yyyyMMddHHmmss'))"
$target = "Arn=$shutdownArn,RoleArn=$schedulerRoleArn,Input='{}'"

# The independent AWS-side closure is installed before either execution surface opens.
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

try {
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
            "--reserved-concurrent-executions", "1",
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
        $openedConcurrency.ReservedConcurrentExecutions -ne 1
    }
    if ($openedApi.DisableExecuteApiEndpoint -or $unexpectedConcurrency) {
        throw "The bounded window did not reach its exact open state"
    }
}
catch {
    & aws apigatewayv2 update-api --api-id $apiId --disable-execute-api-endpoint --region $Region | Out-Null
    & aws lambda put-function-concurrency --function-name $functionName --reserved-concurrent-executions 0 --region $Region | Out-Null
    & aws cloudwatch delete-alarms --alarm-names $alarmName --region $Region | Out-Null
    & aws scheduler delete-schedule --name $scheduleName --group-name $scheduleGroup --region $Region | Out-Null
    throw
}

[pscustomobject]@{
    OpenedAtUtc       = [DateTime]::UtcNow.ToString("O")
    AutomaticCloseUtc = $closeAt.ToString("O")
    RequestTripwire   = $RequestThreshold
    Authentication    = "Cognito JWT with aws-remote-mcp/use"
    ConcurrencyMode   = if ($UseUnreservedConcurrency) { "unreserved-account-cap-10" } else { "reserved-1" }
    ScheduleName      = $scheduleName
}
