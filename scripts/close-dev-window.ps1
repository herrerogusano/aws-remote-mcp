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

& aws apigatewayv2 update-api --api-id $apiId --disable-execute-api-endpoint true --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("disable_api") }

& aws lambda put-function-concurrency --function-name $functionName --reserved-concurrent-executions 0 --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("stop_lambda") }

& aws cloudwatch delete-alarms --alarm-names $alarmName --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) { $failures.Add("delete_traffic_alarm") }

if ($failures.Count -gt 0) {
    throw "Fail-closed cleanup needs attention: $($failures -join ', ')"
}

[pscustomobject]@{
    ClosedAtUtc  = [DateTime]::UtcNow.ToString("O")
    ApiDisabled  = $true
    LambdaStopped = $true
}
