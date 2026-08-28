[CmdletBinding()]
param(
    [ValidateRange(1, 5)]
    [int]$WindowMinutes = 5,
    [ValidateRange(1, 20)]
    [int]$RequestThreshold = 20,
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

$apiId = Get-StackOutput "DevApiId"
$functionName = Get-StackOutput "DevFunctionName"
$shutdownArn = Get-StackOutput "SafetyShutdownFunctionArn"
$schedulerRoleArn = Get-StackOutput "SafetyShutdownSchedulerRoleArn"
$scheduleGroup = Get-StackOutput "SafetyShutdownScheduleGroupName"
$topicArn = Get-StackOutput "SafetyShutdownTopicArn"

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
        "--no-disable-execute-api-endpoint",
        "--region", $Region
    ) | Out-Null
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
    Authentication    = "AWS_IAM"
    ScheduleName      = $scheduleName
}
