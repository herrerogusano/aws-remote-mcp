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
real AWS inventory or external write tools.

## Approved closed deployment

```powershell
sam deploy `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides Environment=dev `
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
The endpoint requires SigV4/AWS IAM authorization.

```powershell
.\scripts\open-dev-window.ps1
```

The maximum window is five minutes. The alarm invokes the safety shutdown after
20 requests in one minute. Lambda concurrency is one. Call only `tools/list`,
`diagnostico`, and `listar_recursos_aws_sintetico`, then close immediately:

```powershell
.\scripts\close-dev-window.ps1
```

Verify again that the API is disabled, concurrency is zero, and the temporary
traffic alarm no longer exists. Inspect sanitized logs and record cold/warm
latency without sending credentials or sensitive application payloads.

## Expected resources

- CloudFormation stack `aws-remote-mcp-dev`;
- one disabled-by-default, IAM-authorized HTTP API and `dev` stage;
- the MCP Lambda, permission and logs, stopped by default;
- an idle safety-shutdown Lambda and logs;
- a safety SNS topic and exact topic policy;
- a dedicated Scheduler group for isolated one-time shutdown schedules;
- three least-privilege IAM roles: MCP execution, shutdown execution, scheduler;
- deployment artifacts in the existing SAM-managed regional S3 bucket.

Only during a validation window, one auto-deleting Scheduler schedule and one
temporary CloudWatch alarm also exist. There is no Cognito, VPC, NAT gateway,
provisioned concurrency, database, queue, secret, custom domain, WAF or PROD.

## Rollback

CloudFormation rolls back a failed create. Removing an accepted deployment needs
the separate destructive approval before:

```powershell
sam delete --stack-name aws-remote-mcp-dev --region eu-west-1
```

The stack owns no business data. Its three log groups are deleted with the stack;
the shared SAM artifact bucket is retained.
