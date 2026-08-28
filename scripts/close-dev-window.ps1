[CmdletBinding()]
param(
    [string]$StackName = "aws-remote-mcp-dev",
    [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Continue"
$alarmName = "aws-remote-mcp-dev-request-kill-switch"
$failures = [Collections.Generic.List[string]]::new()

function Get-StackOutput {
    param([Parameter(Mandatory)][string]$OutputKey)

    $query = "Stacks[0].Outputs[?OutputKey=='$OutputKey'].OutputValue | [0]"
    $value = & aws cloudformation describe-stacks --stack-name $StackName --region $Region --query $query --output text
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw "Unable to read stack output: $OutputKey"
    }
    return "$value".Trim()
}

$apiId = Get-StackOutput "DevApiId"
$functionName = Get-StackOutput "DevFunctionName"
$scheduleGroup = Get-StackOutput "SafetyShutdownScheduleGroupName"

& aws apigatewayv2 update-api --api-id $apiId --disable-execute-api-endpoint --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("disable_api") }

& aws lambda put-function-concurrency --function-name $functionName --reserved-concurrent-executions 0 --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("stop_lambda") }

& aws cloudwatch delete-alarms --alarm-names $alarmName --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("delete_traffic_alarm") }

$scheduleNames = & aws scheduler list-schedules --group-name $scheduleGroup --region $Region --query "Schedules[].Name" --output text
if ($LASTEXITCODE -ne 0) {
    $failures.Add("list_auto_close_schedules")
}
else {
    foreach ($scheduleName in ($scheduleNames -split "\s+")) {
        if (-not [string]::IsNullOrWhiteSpace($scheduleName)) {
            & aws scheduler delete-schedule --name $scheduleName --group-name $scheduleGroup --region $Region | Out-Null
            if ($LASTEXITCODE -ne 0) { $failures.Add("delete_auto_close_schedule") }
        }
    }
}

if ($failures.Count -gt 0) {
    throw "Fail-closed cleanup needs attention: $($failures -join ', ')"
}

[pscustomobject]@{
    ClosedAtUtc  = [DateTime]::UtcNow.ToString("O")
    ApiDisabled  = $true
    LambdaStopped = $true
}
