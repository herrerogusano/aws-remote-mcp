# Project status

Region: `eu-west-1`

## Multi-client increment

On 2026-09-09 the target was clarified as a public portfolio MCP that users can
connect from multiple AI clients. The provider-neutral OAuth increment merged
through PR #39. WorkOS AuthKit is selected for CIMD/DCR onboarding, the AWS
template accepts independent OAuth issuer and authorization-server inputs, and
Lambda no longer assumes Cognito's private `token_use` claim. Exact issuer,
audience, subject and scope checks remain in place. A read-only metadata
validator and bounded external-OAuth opening profile are included.

The free WorkOS staging environment was configured with self-service signup,
CIMD, DCR and the exact DEV resource indicator. Its public OAuth and OIDC
metadata passed the local capability preflight. The profile was then deployed to
DEV through a reviewed non-replacing CloudFormation change set. The deployment
completed `UPDATE_COMPLETE`; subsequent reads confirmed the API disabled,
Lambda concurrency zero, WorkOS issuer, exact resource audience, `openid` scope,
and zero alarms or schedules.

On 2026-09-16 Codex registered through the WorkOS CIMD/DCR-compatible flow,
completed OAuth and discovered the remote tools. A bounded DEV window then ran
`diagnostico` and `listar_inventario_aws`: both returned `ok`; the inventory used
two SDK reads, returned 13 resources and attempted zero external writes. Telegram
and Trello were not called. DEV was closed immediately afterward and the audit
confirmed the API disabled and Lambda concurrency zero. PROD remains unchanged
and closed.

## Resource Explorer increment

The next read-only increment is implemented and verified offline but is not
deployed. It adds `buscar_recursos_aws` over one pre-existing Resource Explorer
view, with a restricted positive query grammar, one request, no pagination,
at most 50 sanitized resources and no account IDs, full ARNs, properties or
tags in results or audit records. The CloudFormation parameter is empty by
default, so both the environment configuration and exact-view IAM grant remain
disabled until a separate DEV setup and deployment review. Cost Explorer is not
part of this increment.

## Current state

The application core, local Streamable HTTP transport, authorization contract
and closed-by-default AWS foundation are implemented. The DEV stack was deployed
and verified in `eu-west-1` on 2026-08-28. A bounded remote validation through
MCP Inspector completed successfully on 2026-09-02, after which every temporary
AWS and local OAuth control returned to its closed state.

The final merged `develop` revision was deployed on 2026-09-09. Its structured
tool audit records and hardened provider-failure behavior are active in closed
DEV. A final direct validation passed tool discovery, diagnostics and bounded
AWS inventory without calling Telegram or Trello. CloudWatch contained the two
expected exact-schema audit records, and the subsequent shutdown audit confirmed
API disablement, Lambda concurrency zero, no alarm and no schedule.

The next application increment is deployed closed: a fixed, bounded AWS
inventory adapter for Lambda and API Gateway v2, its least-privilege IAM policy,
fault tests and validation scripts. The closed deployment completed on
2026-09-03 without invoking the collector. API disablement, concurrency zero,
JWT routes and all independent shutdown invariants were re-audited afterward.
Real inventory validation passed on 2026-09-07: tool discovery, diagnostics and
inventory succeeded through OAuth. Two SDK reads returned seven Lambda functions
and three API Gateway v2 APIs, with no truncation, warnings, errors or writes.
The window closed after approximately 35 seconds and cleanup was independently
verified. No transport recovery retry was needed during this successful run.

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
- Isolated PROD application and Cognito stacks are deployed closed with zero
  users and external integrations disabled. Continuous deployment does not exist.
- The separate Cognito auth stack has five deployed resources, deletion
  protection, enforced threat protection, administrator-only user creation and
  exactly one validation identity.
- The prepared inventory operation accepts no arguments, is fixed to
  `eu-west-1`, makes two non-paginated SDK reads with no retries, returns at most
  20 sanitized resources and performs no writes. Its read IAM is deployed as two
  isolated statements; the execution role has no managed policies.
- The inventory deployment changed no route or persistent service. The API is
  disabled, Lambda concurrency is zero and no alarm/schedule exists after the
  successful real collector validation.

## Account cost posture

The AWS account has a monthly $1 budget with two email notifications from $0.01
actual spend. AWS provides no guaranteed hard spending cap. The project therefore
uses disabled compute/endpoints and brief independently closed test windows as
its primary cost controls.

Cognito Plus costs $0.02 per direct active user with no minimum fee.
Administrator-only creation and the one-user project policy bound the current
tier charge to $0.02 per active month.

## Completion state

On 2026-09-07, real inventory validation stopped after successful OAuth because
Inspector 2.4.0 attempted to restart an already-started Streamable HTTP transport.
The redacted token contract passed issuer, audience, scope, client and access-token
checks. No inventory tool ran. Cleanup independently confirmed API disabled,
concurrency zero, no alarm/schedule, no OAuth temporary directory and no Inspector
process. The wrapper now permits one fresh-process, stored-auth-only discovery
retry for this exact error, after token and elapsed-time checks. This recovery is
tested offline. The subsequent real inventory validation passed without needing
the recovery branch, so that branch has not been exercised against AWS.

The confirmed Telegram and Trello integration profile is deployed in closed
DEV. The Standard SecureString exists at the valid, non-reserved path
`/portfolio/aws-remote-mcp/dev/integrations`; its temporary DPAPI-encrypted local
handoff was deleted after provisioning. The on-demand confirmation table is
active, encrypted, TTL-enabled and capped at one read and write request unit per
second. Its exact three DynamoDB actions and the exact SSM `GetParameter` resource
were independently audited. API Gateway remains disabled, Lambda concurrency is
zero and route throttling remains one request per second with burst one.

The first real external validation completed through direct Lambda invocation
while API Gateway remained disabled. Exactly one confirmed Telegram message and
one confirmed Trello card succeeded. The independent cleanup audit confirmed
Lambda concurrency zero, no automatic-close schedule and no traffic alarm. Two
confirmation records are consumed; one record from a pre-provider validation
failure remains unconsumed until normal TTL deletion.

The secure integration and structured-audit changes have been reviewed, passed
CI and merged into `develop`. The portfolio-ready DEV implementation is
complete and deployed closed. The reviewed implementation is promoted to `main`
and an isolated, empty PROD is also deployed closed. Additional provider writes,
a remotely open environment and automated delivery are optional future changes,
not completion requirements; each remains a separate operational decision.
