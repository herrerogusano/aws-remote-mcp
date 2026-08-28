[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$WindowMinutes = 5,
    [ValidateRange(1, 20)]
    [int]$RequestThreshold = 20,
    [ValidateRange(0.01, 1.00)]
    [decimal]$MaximumCurrentMonthSpendUsd = 0.10,
    [string]$StackName = "aws-remote-mcp-dev",
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

$monthStart = [DateTime]::UtcNow.ToString("yyyy-MM-01")
$tomorrow = [DateTime]::UtcNow.Date.AddDays(1).ToString("yyyy-MM-dd")
$spendText = Invoke-AwsCli @(
    "ce", "get-cost-and-usage",
    "--time-period", "Start=$monthStart,End=$tomorrow",
    "--granularity", "MONTHLY",
    "--metrics", "UnblendedCost",
    "--query", "ResultsByTime[0].Total.UnblendedCost.Amount",
    "--output", "text"
)
$culture = [Globalization.CultureInfo]::InvariantCulture
$currentSpend = [decimal]::Parse("$spendText".Trim(), $culture)
if ($currentSpend -ge $MaximumCurrentMonthSpendUsd) {
    throw "Fail closed: current month spend is already at or above the configured threshold."
}

$apiId = Get-StackOutput "DevApiId"
$functionName = Get-StackOutput "DevFunctionName"
$shutdownArn = Get-StackOutput "SafetyShutdownFunctionArn"
$schedulerRoleArn = Get-StackOutput "SafetyShutdownSchedulerRoleArn"
$scheduleGroup = Get-StackOutput "SafetyShutdownScheduleGroupName"
$topicArn = Get-StackOutput "SafetyShutdownTopicArn"

$closeAt = [DateTime]::UtcNow.AddMinutes($WindowMinutes)
$scheduleName = "aws-remote-mcp-dev-auto-close-$($closeAt.ToString('yyyyMMddHHmmss'))"
$target = @{
    Arn     = $shutdownArn
    RoleArn = $schedulerRoleArn
    Input   = "{}"
} | ConvertTo-Json -Compress

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
    "--dimensions", "Name=ApiId,Value=$apiId", "Name=Stage,Value=dev",
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
    Invoke-AwsCli @(
        "lambda", "put-function-concurrency",
        "--function-name", $functionName,
        "--reserved-concurrent-executions", "1",
        "--region", $Region
    ) | Out-Null
    Invoke-AwsCli @(
        "apigatewayv2", "update-api",
        "--api-id", $apiId,
        "--disable-execute-api-endpoint", "false",
        "--region", $Region
    ) | Out-Null
}
catch {
    & aws apigatewayv2 update-api --api-id $apiId --disable-execute-api-endpoint true --region $Region | Out-Null
    & aws lambda put-function-concurrency --function-name $functionName --reserved-concurrent-executions 0 --region $Region | Out-Null
    throw
}

[pscustomobject]@{
    OpenedAtUtc       = [DateTime]::UtcNow.ToString("O")
    AutomaticCloseUtc = $closeAt.ToString("O")
    RequestTripwire   = $RequestThreshold
    Authentication    = "AWS_IAM"
    ScheduleName      = $scheduleName
}
