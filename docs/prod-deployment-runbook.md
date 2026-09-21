# Closed PROD deployment

The initial deployment completed on 2026-09-09. See
`docs/prod-deployment-evidence.md` for the verified state.

PROD is an isolated, closed-by-default environment deployed only from `main`.
Its initial profile has no users and no Telegram or Trello integration. This
avoids copying identity, credentials or confirmation state across environments.

## Resources and cost posture

The two stacks are `aws-remote-mcp-prod` and `aws-remote-mcp-auth-prod`. Resource
names, logs, API, Lambda roles, shutdown controls and Cognito are separate from
DEV. The application deploys with `EnableExternalIntegrations=false` and
`EnableCostExplorer=false`, so PROD has no confirmation table, provider
parameter access, provider tools or Cost Explorer permission/tool.

The empty Cognito Plus pool has no monthly active user. API Gateway and Lambda
remain disabled while idle. Log groups retain data for seven days. No alarm or
schedule exists outside a separately designed PROD opening procedure; the DEV
opening scripts must never be pointed at PROD.

## Initial closed bootstrap

The API identifier is allocated by the first application-stack deployment, while
the final Cognito resource server needs that API URI. Resolve this dependency in
three closed steps:

1. Create the application stack with a syntactically valid existing issuer and
   audience only as bootstrap parameters. The template fixes the endpoint as
   disabled and Lambda concurrency as zero, so the bootstrap cannot serve a
   request.
2. Create the PROD authentication stack against the new `McpEndpoint` output.
3. Immediately update the application stack with the PROD issuer, audience and
   scope.

Both application deployments must explicitly use:

```text
Environment=prod
EnableExternalIntegrations=false
IntegrationConfigParameterName=/portfolio/aws-remote-mcp/prod/integrations
EnableCostExplorer=false
ResourceExplorerViewArn=<empty>
```

Use a unique PROD Cognito domain prefix. Keep `ResourceExplorerViewArn` empty;
do not create a PROD user, enable TOTP enrollment, create the provider
parameter or reuse DEV credentials.

## Required verification

After the final update, require all of the following:

- both CloudFormation stacks are complete;
- the PROD API endpoint is disabled;
- PROD Lambda reserved concurrency is zero, memory is 128 MB and timeout is ten
  seconds;
- stage rate and burst limits are 1/1;
- `/mcp` uses the exact PROD Cognito issuer, PROD endpoint audience and
  `<PROD endpoint>/use` scope;
- the Cognito pool has deletion protection, enforced threat protection, required
  software-token MFA, administrator-only creation and zero users;
- no PROD confirmation table or integration parameter exists;
- `EnableCostExplorer=false`, both Cost Explorer Lambda environment values are
  false/empty (`COST_EXPLORER_ENABLED` and `COST_EXPLORER_BILLING_VIEW_ARN`),
  and the role has no `ce:GetCostAndUsage` permission;
- no PROD request alarm or one-time shutdown schedule exists;
- neither DEV stack changed during the deployment.

Do not invoke PROD Lambda or open its API as part of initial creation. A future
live PROD validation requires its own reviewed scripts and operational decision.
