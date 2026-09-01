[CmdletBinding()]
param(
    [string]$Region = "eu-west-1",
    [string]$AppStack = "aws-remote-mcp-dev",
    [string]$AuthStack = "aws-remote-mcp-auth-dev",
    [string]$DomainPrefix = "remote-mcp-dev-hg",
    [string]$Username = "portfolio-admin"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$templatePath = Join-Path $repoRoot "auth-template.yaml"
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$helperPath = Join-Path $PSScriptRoot "enroll_cognito_totp.py"

foreach ($requiredPath in @($templatePath, $pythonPath, $helperPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file not found: $requiredPath"
    }
}

$appOutputs = aws cloudformation describe-stacks `
    --stack-name $AppStack `
    --region $Region `
    --query "Stacks[0].Outputs" `
    --output json | ConvertFrom-Json
$mcpResource = ($appOutputs | Where-Object OutputKey -eq "DevMcpEndpoint").OutputValue
$apiId = ($appOutputs | Where-Object OutputKey -eq "DevApiId").OutputValue
$functionName = ($appOutputs | Where-Object OutputKey -eq "DevFunctionName").OutputValue

$authOutputs = aws cloudformation describe-stacks `
    --stack-name $AuthStack `
    --region $Region `
    --query "Stacks[0].Outputs" `
    --output json | ConvertFrom-Json
$poolId = ($authOutputs | Where-Object OutputKey -eq "UserPoolId").OutputValue
$clientId = ($authOutputs | Where-Object OutputKey -eq "InspectorClientId").OutputValue
$authorizationServer = `
    ($authOutputs | Where-Object OutputKey -eq "AuthorizationServer").OutputValue

if ($poolId -notmatch "^eu-west-1_[A-Za-z0-9]+$") {
    throw "Unexpected Cognito pool identifier"
}
if ($mcpResource -notmatch "^https://[^?#]+/mcp$") {
    throw "Unexpected MCP resource URI"
}

$users = aws cognito-idp list-users `
    --user-pool-id $poolId `
    --region $Region `
    --limit 2 `
    --output json | ConvertFrom-Json
if (@($users.Users).Count -ne 1 -or $users.Users[0].Username -ne $Username) {
    throw "Enrollment requires exactly the expected validation identity"
}

$api = aws apigatewayv2 get-api --api-id $apiId --region $Region `
    --output json | ConvertFrom-Json
$concurrency = aws lambda get-function-concurrency `
    --function-name $functionName `
    --region $Region `
    --output json | ConvertFrom-Json
if (-not $api.DisableExecuteApiEndpoint -or $concurrency.ReservedConcurrentExecutions -ne 0) {
    throw "Refusing enrollment unless the MCP endpoint and compute are closed"
}

function Deploy-EnrollmentGate([string]$enabled) {
    aws cloudformation deploy `
        --template-file $templatePath `
        --stack-name $AuthStack `
        --region $Region `
        --parameter-overrides `
            Environment=dev `
            CognitoDomainPrefix=$DomainPrefix `
            McpResourceUri=$mcpResource `
            InspectorCallbackUrl=http://127.0.0.1:6276/oauth/callback `
            TotpEnrollmentEnabled=$enabled `
        --no-fail-on-empty-changeset `
        --tags environment=dev project=aws-remote-mcp
    if ($LASTEXITCODE -ne 0) {
        throw "CloudFormation failed while setting enrollment gate to $enabled"
    }
}

try {
    Deploy-EnrollmentGate "true"
    & $pythonPath $helperPath `
        --authorization-server $authorizationServer `
        --client-id $clientId `
        --region $Region
    if ($LASTEXITCODE -ne 0) {
        throw "Local TOTP enrollment helper failed"
    }
}
finally {
    Deploy-EnrollmentGate "false"
    $scopes = aws cognito-idp describe-user-pool-client `
        --user-pool-id $poolId `
        --client-id $clientId `
        --region $Region `
        --query "UserPoolClient.AllowedOAuthScopes" `
        --output json | ConvertFrom-Json
    if (@($scopes).Count -ne 1 -or $scopes[0] -ne "aws-remote-mcp/use") {
        throw "The temporary enrollment scope was not removed"
    }
}

Write-Output "TOTP enrollment finished and the temporary scope is closed."
