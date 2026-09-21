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
sam build --template-file template.yaml `
  --build-dir .aws-sam/build-current `
  --beta-features
```

The template accepts only `Environment=dev`. It needs no secrets and adds only
the base inventory reads documented in `docs/aws-inventory.md`; Resource
Explorer is separately disabled unless an exact, pre-existing view ARN is
explicitly supplied. Cost Explorer is also disabled by default; this runbook
always deploys with `EnableCostExplorer=false`. The Cognito stack must already
exist because its exact issuer and the existing API identifier are deployment
inputs.

Before deployment, inspect `.aws-sam/build-current/template.yaml` and require the
`$default` stage, all three expected routes, `McpRequiredScope` and the two base
inventory IAM statements. With `ResourceExplorerViewArn` empty, verify that the
generated policy omits Resource Explorer permissions. If it is explicitly
configured, require exactly one additional `resource-explorer-2:Search` action
on that exact view ARN, constrained to `eu-west-1` and
`resource-explorer-2:Operation=Search`. Always name this fresh generated template
explicitly; an implicit `sam deploy` can reuse a stale
`.aws-sam/build/template.yaml`.

With `EnableCostExplorer=false`, require that the generated role has no Cost
Explorer action, `COST_EXPLORER_ENABLED` is `false` and
`COST_EXPLORER_BILLING_VIEW_ARN` is empty. If the switch is separately approved
as `true`, require only `ce:GetCostAndUsage`, in its own statement on
`Resource: "*"` because AWS evaluates this operation against its service
endpoint ARN (the observed form is
`arn:aws:ce:us-east-1:<account>:/GetCostAndUsage`); require
`COST_EXPLORER_BILLING_VIEW_ARN` to contain that exact ARN and to be passed
explicitly to the API. No Cost Explorer API call is part of deployment or this
preflight.

## Inventory IAM/deployment gate

The inventory closed deployment changes the MCP execution role. It adds only:

- `lambda:ListFunctions` on `Resource: "*"`, because AWS provides no resource
  type for this list action, constrained by `aws:RequestedRegion=eu-west-1`;
- `apigateway:GET` on the exact regional `/apis` collection ARN;
- `cloudformation:ListStackResources` on only the four exact project stack ARN
  patterns (`aws-remote-mcp-dev`, `aws-remote-mcp-prod`,
  `aws-remote-mcp-auth-dev` and `aws-remote-mcp-auth-prod`), constrained by
  `aws:RequestedRegion=eu-west-1`.

The CloudFormation action supports resource-level scoping to stack ARNs. It adds
no account-wide stack listing, stack description, mutation action, route, secret
or persistent-cost service. The API and Lambda remain disabled during deployment.
This role change still requires explicit approval before running the command
below.

The default keeps `ResourceExplorerViewArn` empty, so no Resource Explorer
permission is included. To opt in, a separate explicit IAM/deployment review
must provide the exact ARN of a view that already exists in `eu-west-1`.
This project does not enable Resource Explorer or create an index, view,
service-linked role, or other AWS resource. Never use `AWSResourceExplorerFullAccess`
or a managed read-only policy. Until that opt-in is separately approved, keep
the parameter empty in DEV and PROD.

Keep `EnableCostExplorer=false` for this standard closed deployment. A later
Cost Explorer opt-in requires separate approval because each API page costs
`$0.01`. It adds only the exact primary-billing-view read permission and reuses
the single-use confirmation table for both confirmations and an atomic global
three-attempt UTC-month quota (`$0.03` maximum API-request charge from this MCP).
It neither enables the API endpoint nor activates Cost Explorer at the account
level. Do not use it in the ordinary Inspector or direct-Lambda validation
procedure.

## Approved closed deployment

```powershell
$auth = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-auth-dev `
  --region eu-west-1 `
  --output json | ConvertFrom-Json
$issuer = ($auth.Stacks[0].Outputs | Where-Object OutputKey -eq 'Issuer').OutputValue
$authorizationServer = $issuer

$app = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --output json | ConvertFrom-Json
$apiId = ($app.Stacks[0].Outputs | Where-Object OutputKey -eq 'DevApiId').OutputValue
$audience = "https://$apiId.execute-api.eu-west-1.amazonaws.com/mcp"
$requiredScope = "$audience/use"

sam deploy `
  --template-file .aws-sam/build-current/template.yaml `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    Environment=dev `
    OAuthIssuer=$issuer `
    OAuthAuthorizationServer=$authorizationServer `
    McpTokenAudience=$audience `
    McpRequiredScope=$requiredScope `
    EnableCostExplorer=false `
    "ResourceExplorerViewArn=" `
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
15 requests in one minute. The generic opener prefers reserved concurrency one.
The Inspector wrapper uses the reviewed unreserved fallback because this
reduced-quota account cannot allocate a reservation; it refuses to proceed
unless both Service Quotas and Lambda account settings report a regional cap and
unreserved pool of exactly 10. This mode also refuses a request tripwire above
15. Call only `tools/list`,
`diagnostico`, and `listar_inventario_aws`, then close immediately:

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
most five minutes with a 15-request tripwire, runs only tool discovery, the
diagnostic and bounded inventory tools, requires exactly two downstream reads
and no more than 20 returned resources, then closes AWS and deletes OAuth state
in `finally`.
After opening, it permits at most two five-second metadata probes and refuses to
start OAuth until the API Gateway data plane returns the exact MCP resource.
Do not run the individual opener for this validation; the wrapper owns the whole
lifecycle.

For the exact Inspector 2.4.0 already-started transport error after OAuth, the
wrapper permits one fresh `tools/list --stored-auth-only` process. It first
checks the stored token contract and remaining validity, and requires fewer than
180 seconds elapsed since beginning the opening sequence. This may add discovery
traffic within the same 15-request tripwire; the deadline is never extended.
Other failures and failed recovery close immediately. Tool calls are not retried.

This existing validation wrapper covers the original two-service inventory
only. Do not call the separate Resource Explorer tool through this procedure;
its IAM opt-in and closed-state behavior need their own explicit deployment and
validation review first.

## API-closed Lambda validation

If the account quota cannot allocate reserved concurrency one, do not weaken
unrelated Lambda reservations. The narrower validation keeps API Gateway
disabled, installs an AWS-side five-minute deadline, performs exactly three
direct invocations including the two-read bounded inventory call, and restores
concurrency zero in `finally`:

```powershell
.\scripts\validate-direct-lambda.ps1
```

This proves the deployed Lambda/MCP and execution-role contract but does not
claim to prove the API Gateway JWT data path. That remains a separate validation
decision.

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
- three least-privilege IAM roles: MCP execution with two base inventory reads
  and, only when explicitly configured, one view-scoped Resource Explorer
  search; shutdown execution; scheduler;
- deployment artifacts in the existing SAM-managed regional S3 bucket.

The on-demand confirmation table exists only when external integrations or
Cost Explorer are enabled. When both `EnableExternalIntegrations` and
`EnableCostExplorer` are false, no table or confirmation permissions are
created. An existing DEV profile may keep external integrations enabled while
Cost Explorer remains independently disabled.

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
the shared SAM artifact bucket is retained. A separately managed Resource
Explorer view or index is outside this stack and is neither modified nor
deleted by its rollback or removal.
