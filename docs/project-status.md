# Project status

Region: `eu-west-1`

## Current state

The application core, local Streamable HTTP transport, authorization contract
and closed-by-default AWS foundation are implemented. The DEV stack was deployed
and verified in `eu-west-1` on 2026-08-28. A bounded remote validation through
MCP Inspector completed successfully on 2026-09-02, after which every temporary
AWS and local OAuth control returned to its closed state.

The deployed Lambda/MCP contract was validated directly on 2026-08-28 while the
API remained disabled. All three bounded synthetic calls succeeded and the
function was returned to reserved concurrency zero immediately afterward.

The production-shaped OAuth foundation was deployed and verified on 2026-08-28:
Cognito Plus with enforced threat protection, a public pre-registered MCP
Inspector client, PKCE, audience binding, five-minute access tokens, refresh
rotation and mandatory TOTP. Its issuer, exact audience and required custom scope
are connected to the still-closed API through a JWT authorizer. One
administrator-created validation identity was added on 2026-09-01
with delivery suppressed and no email or phone attributes. Its first-login
password change and software-token MFA enrollment are complete. Enrollment was
performed locally without opening the API, and the temporary Cognito scope was
removed afterward.

## Deployment posture

- DEV stack deployed with every CloudFormation resource complete.
- Default API endpoint verified disabled in AWS.
- `POST /mcp` requires Cognito JWT authorization with the exact audience and
  resource-bound `<MCP endpoint>/use` scope.
- Lambda independently checks the validated access-token claim contract and
  removes the bearer header before the MCP application is constructed.
- Public RFC 9728 metadata has GET/OPTIONS routes; the entire API remains
  unreachable while its default endpoint is disabled.
- The API uses the `$default` stage so its endpoint and well-known metadata URI
  have standards-compatible paths without a stage prefix.
- MCP Lambda verified at reserved concurrency zero, 128 MB and 10-second timeout.
- Stage throttling verified at rate 1 request/second and burst 1.
- Five-minute signed validation window has scheduled and volume-based shutdown.
- The regional Lambda quota is the reduced-account value 10. AWS rejected the
  minimal request for 11 because its quota API accepts only values above the
  standard 1,000; the Inspector wrapper therefore permits unreserved execution
  only while the account cap remains exactly 10.
- The independent five-minute shutdown path was exercised on 2026-09-02. The
  authentication callback timed out without remote MCP calls; AWS restored the
  disabled API, concurrency zero, no alarm and no remaining schedule at the
  deadline.
- A subsequent authenticated attempt proved issuer, scope, access-token type
  and client ID correct, but Cognito's classic hosted UI omitted the requested
  resource audience. The prepared managed-login v2 update preserves strict
  endpoint audience checks instead of weakening authorization to client ID.
- Managed login then enforced that custom scopes belong to the requested
  resource. The coordinated update now uses the MCP endpoint as Cognito's
  resource-server identifier and derives its sole scope as `<MCP endpoint>/use`.
- Managed Login v2 is deployed with Cognito-provided branding. A real
  authorization-code + PKCE + TOTP flow produced an endpoint-bound access token;
  Inspector discovered both tools and successfully called `diagnostico` and
  `listar_recursos_aws_sintetico` without external writes.
- The validation wrapper closed the API and Lambda immediately after success.
  An independent audit confirmed concurrency zero, no alarm, no schedule, no
  temporary OAuth directory and no remaining Inspector process.
- No temporary alarm or automatic-close schedule is active while closed.
- All three execution roles have only inline, resource-specific policies and no
  attached managed policy.
- Direct validation evidence: one cold invocation at 1,022 ms plus 2,150 ms
  initialization, two warm invocations at 133 ms and 89 ms, and 108 MB maximum
  memory used out of 128 MB.
- PROD and continuous deployment do not exist.
- The separate Cognito auth stack has five deployed resources, deletion
  protection, enforced threat protection, administrator-only user creation and
  exactly one validation identity.

## Account cost posture

The AWS account has a monthly $1 budget with two email notifications from $0.01
actual spend. AWS provides no guaranteed hard spending cap. The project therefore
uses disabled compute/endpoints and brief independently closed test windows as
its primary cost controls.

Cognito Plus costs $0.02 per direct active user with no minimum fee.
Administrator-only creation and the one-user project policy bound the current
tier charge to $0.02 per active month.

## Next decision

Keep DEV closed by default. Any future remote validation must use the same
bounded wrapper and begin from the independently audited state: API disabled,
Lambda concurrency zero and no temporary shutdown controls left behind.
