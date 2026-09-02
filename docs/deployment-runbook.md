# DEV deployment runbook

Deployment uses two separate approvals. The first permits only a closed stack;
a later explicit approval permits one tightly bounded validation window.

## Preflight

```powershell
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
sam validate --lint --region eu-west-1
sam build --beta-features
```

The template accepts only `Environment=dev`. It needs no secrets and exposes no
real AWS inventory or external write tools. The Cognito stack must already exist
because its exact issuer and the existing API identifier are deployment inputs.

## Approved closed deployment

```powershell
$auth = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-auth-dev `
  --region eu-west-1 `
  --output json | ConvertFrom-Json
$issuer = ($auth.Stacks[0].Outputs | Where-Object OutputKey -eq 'Issuer').OutputValue

$app = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --output json | ConvertFrom-Json
$apiId = ($app.Stacks[0].Outputs | Where-Object OutputKey -eq 'DevApiId').OutputValue
$audience = "https://$apiId.execute-api.eu-west-1.amazonaws.com/mcp"
$requiredScope = "$audience/use"

sam deploy `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    Environment=dev `
    CognitoIssuer=$issuer `
    McpTokenAudience=$audience `
    McpRequiredScope=$requiredScope `
  --no-confirm-changeset `
  --no-fail-on-empty-changeset
```

After deployment, verify both fail-closed invariants before doing anything else:

```powershell
aws apigatewayv2 get-api --api-id <DevApiId> --region eu-west-1
aws lambda get-function-concurrency --function-name aws-remote-mcp-dev --region eu-west-1
```

`DisableExecuteApiEndpoint` must be `true` and reserved concurrency must be `0`.
Do not open the endpoint as part of the closed-stack deployment.

## Separately approved validation window

The opener performs no billable Cost Explorer query. It creates an auto-deleting
AWS Scheduler deadline and a CloudWatch request alarm before enabling anything.
The MCP route requires a Cognito access token with the exact endpoint audience
and `<MCP endpoint>/use` scope. The RFC 9728 metadata route is public only while
the whole API endpoint is enabled.

```powershell
.\scripts\open-dev-window.ps1
```

The maximum window is five minutes. The alarm invokes the safety shutdown after
20 requests in one minute. The generic opener prefers reserved concurrency one.
The Inspector wrapper uses the reviewed unreserved fallback because this
reduced-quota account cannot allocate a reservation; it refuses to proceed
unless both Service Quotas and Lambda account settings report a regional cap and
unreserved pool of exactly 10. This mode also refuses a request tripwire above
15. Call only `tools/list`,
`diagnostico`, and `listar_recursos_aws_sintetico`, then close immediately:

```powershell
.\scripts\close-dev-window.ps1
```

Verify again that the API is disabled, concurrency is zero, and the temporary
traffic alarm no longer exists. Inspect sanitized logs and record cold/warm
latency without sending credentials or sensitive application payloads.

After TOTP enrollment, the complete Inspector validation is wrapped in one
command:

```powershell
.\scripts\validate-inspector-window.ps1
```

It performs all closed-state, quota and MFA preflights, prepares the pinned
Inspector before opening AWS, uses a private temporary OAuth store, opens at
most five minutes with a 15-request tripwire, runs only tool discovery and the
two safe synthetic tools, then closes AWS and deletes OAuth state in `finally`.
After opening, it permits at most two five-second metadata probes and refuses to
start OAuth until the API Gateway data plane returns the exact MCP resource.
Do not run the individual opener for this validation; the wrapper owns the whole
lifecycle.

## API-closed Lambda validation

If the account quota cannot allocate reserved concurrency one, do not weaken
unrelated Lambda reservations. The narrower validation keeps API Gateway
disabled, installs an AWS-side five-minute deadline, performs exactly three
direct synthetic invocations, and restores concurrency zero in `finally`:

```powershell
.\scripts\validate-direct-lambda.ps1
```

This proves the deployed Lambda/MCP contract but does not claim to prove the
API Gateway IAM data path. That remains a separate validation decision.

## Expected resources

- CloudFormation stack `aws-remote-mcp-dev`;
- one disabled-by-default HTTP API with a Cognito JWT authorizer and default
  stage;
- one JWT-protected `POST /mcp` route plus public GET/OPTIONS protected-resource
  metadata routes;
- the MCP Lambda, permission and logs, stopped by default;
- an idle safety-shutdown Lambda and logs;
- a safety SNS topic and exact topic policy;
- a dedicated Scheduler group for isolated one-time shutdown schedules;
- three least-privilege IAM roles: MCP execution, shutdown execution, scheduler;
- deployment artifacts in the existing SAM-managed regional S3 bucket.

Only during a validation window, one auto-deleting Scheduler schedule and one
temporary CloudWatch alarm also exist. This app stack contains no Cognito, VPC,
NAT gateway, provisioned concurrency, database, queue, secret, custom domain,
WAF or PROD; Cognito is isolated in the separate zero-user auth stack.

## Rollback

CloudFormation rolls back a failed create. Removing an accepted deployment needs
the separate destructive approval before:

```powershell
sam delete --stack-name aws-remote-mcp-dev --region eu-west-1
```

The stack owns no business data. Its three log groups are deleted with the stack;
the shared SAM artifact bucket is retained.
