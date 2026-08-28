# DEV deployment runbook

This runbook is prepared for Phase 4. Do not run the deployment command until
Gate A is explicitly approved.

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

The template allows only `Environment=dev`. The Lambda artifact is Linux x86_64,
the function exposes only safe synthetic tools, and no secrets are required.

## Deployment after Gate A

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

Capture the `DevMcpEndpoint`, `DevApiId`, and `DevFunctionName` stack outputs.
Call only `tools/list`, `diagnostico`, and `listar_recursos_aws_sintetico`.
Confirm that responses declare `environment=dev` and
`external_side_effects=false`; do not send credentials or sensitive payloads.

Inspect the two 7-day log groups for request identifiers, status, latency, and
sanitized application/system events. Record cold and warm request latency.

## Expected resources

- CloudFormation stack `aws-remote-mcp-dev`;
- one HTTP API and `dev` stage;
- one Lambda function and one Lambda permission;
- one IAM execution role with only write access to its own log streams;
- two CloudWatch log groups with seven-day retention;
- deployment artifacts in the account's SAM-managed regional S3 bucket.

No Cognito, VPC, NAT gateway, provisioned concurrency, database, queue, secret,
custom domain, WAF, or production environment is created.

## Rollback

CloudFormation rolls back a failed create automatically. For an accepted but
unwanted deployment, first capture the stack events and logs, then request the
separate destructive approval required before running:

```powershell
sam delete --stack-name aws-remote-mcp-dev --region eu-west-1
```

The stack owns no business data. Its two log groups are configured for deletion
with the stack. The shared SAM artifact bucket, if present, is not deleted by
this command.
