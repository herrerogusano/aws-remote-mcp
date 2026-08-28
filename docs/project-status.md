# Project status

Region: `eu-west-1`

## Current state

The application core, local Streamable HTTP transport, authorization contract
and closed-by-default AWS foundation are implemented. The DEV stack was deployed
and verified in `eu-west-1` on 2026-08-28. No remote validation session or
external integration has been activated.

The deployed Lambda/MCP contract was validated directly on 2026-08-28 while the
API remained disabled. All three bounded synthetic calls succeeded and the
function was returned to reserved concurrency zero immediately afterward.

The production-shaped OAuth profile is now selected and prepared locally:
Cognito Lite with a public pre-registered MCP Inspector client, PKCE, audience
binding, five-minute access tokens and mandatory TOTP. No Cognito resource or
user has been created.

## Deployment posture

- DEV stack deployed with every CloudFormation resource complete.
- Default API endpoint verified disabled in AWS.
- The only route is `POST /mcp`, verified with AWS IAM authorization.
- MCP Lambda verified at reserved concurrency zero, 128 MB and 10-second timeout.
- Stage throttling verified at rate 1 request/second and burst 1.
- Five-minute signed validation window has scheduled and volume-based shutdown.
- No temporary alarm or automatic-close schedule is active while closed.
- All three execution roles have only inline, resource-specific policies and no
  attached managed policy.
- Direct validation evidence: one cold invocation at 1,022 ms plus 2,150 ms
  initialization, two warm invocations at 133 ms and 89 ms, and 108 MB maximum
  memory used out of 128 MB.
- PROD and continuous deployment do not exist.

## Account cost posture

The AWS account has a monthly $1 budget with two email notifications from $0.01
actual spend. AWS provides no guaranteed hard spending cap. The project therefore
uses disabled compute/endpoints and brief independently closed test windows as
its primary cost controls.

## Next decision

Review the separate Cognito template, IAM-free user-pool resources, cost posture
and retained rollback behavior. Deploying it and creating one administrator-only
user require explicit authorization. API Gateway remains IAM-protected and
disabled until a later gate.
