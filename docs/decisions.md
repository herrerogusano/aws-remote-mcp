# Decisions

## D-001 - Python 3.13 and uv

Use Python 3.13 with `uv` and commit `uv.lock`. Python 3.13 is available in the
local environment, supported by the current MCP SDK, and supported by AWS Lambda
through 2029. Keeping a single minor version makes local, CI, and future Lambda
behavior easier to reproduce.

Sources checked 2026-08-28:

- https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html
- https://pypi.org/project/mcp/
- https://docs.astral.sh/uv/guides/integration/github/

## D-002 - MCP SDK 2.x

Use the official `mcp` Python package with `mcp>=2.1.1,<3`. Version 2.1.1 is the
current stable release and supports the 2026-07-28 protocol specification,
including Streamable HTTP.

## D-003 - CI before runtime features

Every pull request to `develop` or `main` runs locked installation, formatting,
linting, strict typing, compilation, and unit tests. These checks have no live
AWS or external-service dependency.

## D-004 - Mandatory environment mapping

`develop` maps to DEV and `main` maps to PROD. Feature work branches from and
returns to `develop`; production changes arrive only through a promotion pull
request. Only the closed-by-default DEV foundation is currently deployed.

## D-005 - Transport-independent application core

MCP and HTTP adapters call application services rather than contain tool logic.
The core depends only on adapter protocols and is tested with deterministic
in-memory fakes and no network access.

## D-006 - Fail-closed operation registry

Only positively registered `free_verified_read` operations may run
automatically. Controlled-billable, write, sensitive-read, unknown, and absent
operations are blocked. Later AWS collectors must expand the same registry with
current evidence instead of bypassing it.

## D-007 - Scoped single-use confirmations

Confirmation tokens are opaque and short-lived. Server-side records bind their
hash to caller fingerprint, action, canonical payload digest, expiry, and use
state. A confirmation is consumed before the downstream write begins; an
ambiguous failure therefore cannot be retried with the same token.

## D-008 - One write and bounded output

Each execution counter permits at most one external-write attempt. Adapter
results exceeding the configured byte limit are replaced by a normalized error,
and downstream adapter errors cross the boundary only as sanitized codes and
messages.

## D-009 - Modern stateless Streamable HTTP

Use the official MCP Python SDK 2.1.1 ASGI application with current protocol
revision 2026-07-28, `stateless_http=True`, and `json_response=True`. This avoids
session affinity and long-lived SSE while preserving real MCP semantics, matching
the intended Lambda/API Gateway request model.

## D-010 - Local transport boundary

The local server binds to `127.0.0.1`, uses one `/mcp` endpoint, enforces a
64 KiB body cap, and explicitly allowlists local Host and Origin values. Only a
safe diagnostic, synthetic AWS inventory, and Telegram/Trello preview tools are
registered.

## D-011 - Lambda adaptation preference

Use Mangum because it directly adapts API Gateway HTTP API v2 events to the
unchanged official ASGI app with a small Python dependency. Repeated lifespan
behavior is tested. AWS Lambda Web Adapter remains the fallback before any
custom event/protocol bridge.

## D-012 - OAuth protected-resource contract

Expose RFC 9728 metadata and return MCP-aligned bearer challenges. Authentication
failures are 401; valid tokens with insufficient scope are 403. Challenges name
the protected-resource metadata URI and `<MCP resource URI>/use` scope.

## D-013 - Audience-bound access tokens

Accept only access tokens whose issuer, signature, expiry and audience are valid
for this MCP resource. Normalize only issuer, subject and scopes for application
services. Never forward the inbound token to AWS, Telegram or Trello.

## D-014 - Cognito requires pre-registration compatibility

Cognito plus API Gateway JWT authorization remains the AWS-native candidate.
Use authorization code + PKCE, custom scope and resource binding. Cognito does
not offer current MCP Client ID Metadata Document support or standard DCR, so
the target client must accept a pre-registered client ID/callback. Otherwise
An authorization architecture review must compare alternatives.

## D-015 - Fresh stateless ASGI lifecycle per Lambda invocation

Use Mangum 0.22 with API Gateway HTTP API v2 and create a fresh official MCP
ASGI app per Lambda invocation. A process-global app cannot re-enter the SDK
session-manager lifespan on a repeated warm invocation, while disabling lifespan
leaves its task group uninitialized. Fresh construction preserves the official
SDK lifecycle and succeeds across repeated events; its overhead will be measured
in DEV before considering Lambda Web Adapter.

Build the Linux x86_64 artifact with SAM's preview `python-uv` build method and a
runtime-only lock under `src/`. CI opts into that builder explicitly. This avoids
host-platform resolution and excludes Windows-only dependencies.

## D-016 - Closed-by-default DEV deployment skeleton

The first deployment is DEV-only and creates no callable endpoint. The default
API Gateway endpoint is disabled, its route requires AWS IAM authorization, and
the MCP Lambda has reserved concurrency zero. This temporary infrastructure guard
is independent from the final MCP OAuth design.

A separately approved test window is at most five minutes. Its opening script
installs an AWS-side one-time shutdown and creates a request-volume alarm. Only
then does it set Lambda concurrency to one and enable the endpoint. The API
target is 1 request/second with burst 1;
Lambda is 128 MB with a 10-second timeout. Twenty requests in one minute, the
five-minute deadline, or the explicit close script invokes the fail-closed path.

AWS Budgets and API Gateway throttles are monitoring/target controls, not hard
spending caps. The existing account-wide monthly budget alerts two email
subscribers after $0.01 actual spend. Immediate project protection therefore
comes from keeping the endpoint disabled and compute at zero outside the bounded
test window rather than claiming that AWS can guarantee a fixed maximum bill.
Cost Explorer is excluded from runtime and operational scripts because each API
request costs $0.01 and its data is delayed.

## D-017 - API-closed validation when reserved concurrency is unavailable

The account's regional Lambda quota is 10 and cannot allocate reserved
concurrency one while preserving AWS's required unreserved pool. Do not change
unrelated functions or request a larger concurrency quota merely to run a test.

Validate the deployed Lambda/MCP contract through exactly three direct synthetic
invocations while API Gateway remains disabled. Install an independent
five-minute shutdown first, remove concurrency zero only for the calls, and
restore it in `finally`. Treat this as Lambda boundary evidence, not evidence for
the API Gateway IAM path.

## D-018 - Cognito with a pre-registered official Inspector client

Use Cognito Plus as the first authorization server profile and the official MCP
Inspector CLI/TUI as the controlled validation client. The client is public,
pre-registered to one exact loopback callback, and uses authorization code with
S256 PKCE. Tokens require the `<MCP resource URI>/use` scope and the exact MCP URI as
their audience through Cognito resource binding.

Disable self-registration and message-based authentication. Require TOTP, keep
access tokens at five minutes, rotate one-day refresh tokens with no grace reuse
period, use the free Cognito domain and enforce Plus threat protection. Plus has
no free tier, but its $0.02 per direct MAU price is bounded to $0.02 per month by
the administrator-only single-user project policy; zero users cost $0.
Cognito's lack of CIMD and DCR is an explicit interoperability boundary; never
add a custom registration shim. Re-evaluate a native MCP authorization provider
if a future client cannot
accept pre-registration.

## D-019 - JWT route and stage-less OAuth resource URI

Replace the temporary IAM route guard with API Gateway's native JWT authorizer.
Require the Cognito issuer, exact MCP endpoint audience and
`<MCP resource URI>/use` route scope; the required scope prevents Cognito ID tokens
from satisfying the route. Keep RFC 9728 metadata public but expose no other
unauthenticated application route.

At the Lambda boundary, require matching validated `iss`, `aud`, `scope`,
`token_use=access` and a non-empty subject, then discard the Authorization header
before it reaches the ASGI application. This is defense in depth behind API
Gateway and minimizes bearer-token propagation.

Use API Gateway's `$default` stage so the canonical MCP URI is `/mcp` and its
well-known metadata URI can follow the standard host-root insertion rule without
a stage prefix. This supersedes only the temporary authorization and named-stage
parts of D-016; endpoint disablement, zero concurrency, throttling and independent
shutdown controls remain unchanged.

## D-020 - Account-cap fallback for the remote validation window

The account's applied regional Lambda concurrency quota is 10. AWS rejects
reserved concurrency one because the reduced profile must retain all 10 as
unreserved capacity. A request for the minimal quota 11 was attempted, but the
Service Quotas API accepts only desired values above the standard quota 1,000;
do not request 1,001 merely to run one validation.

For the bounded Inspector validation only, remove concurrency zero after all
shutdown controls are armed and refuse the fallback unless the applied regional
quota, Lambda account limit and unreserved pool all remain exactly 10. JWT
authorization, stage throttle 1/1, a tripwire no higher than 15 requests and the
five-minute independent deadline remain mandatory. Restore reserved concurrency
zero in every close path.

## D-021 - Managed login is required for Cognito resource binding

The classic hosted UI accepted the OAuth `resource` parameter but issued an
access token without the corresponding `aud` claim, which API Gateway correctly
rejected. Keep endpoint-specific audience validation at both API Gateway and
Lambda rather than weakening the contract to client-ID-only validation.

Use Cognito managed login version 2 with a Cognito-provided default branding
style. This changes only the existing authentication UI resources and preserves
the same Plus tier, public PKCE client, callback, scopes, MFA and token lifetime.

## D-022 - Cognito resource identifier and custom scope share the MCP URI

Cognito managed login rejects resource-bound authorization when a custom scope
belongs to a different resource-server identifier. Use the canonical MCP
endpoint as the Cognito resource-server identifier and derive the sole custom
scope as `<MCP endpoint>/use`.

Deploy this scope atomically across the Cognito app client, RFC 9728 metadata,
API Gateway route authorizer, validation tooling and Lambda's defensive claim
check. Do not keep a project-name scope beside a URL resource indicator.

## D-023 - Two-call bounded AWS inventory

Implement the first real AWS inventory as one fixed adapter operation over
Lambda `ListFunctions` and API Gateway v2 `GetApis` in `eu-west-1`. Each tool
execution makes exactly one non-paginated request per service, requests no more
than ten resources per service and configures the SDK for no retries. Caller
arguments cannot select services, regions, operations, pagination or limits.

Permit only `lambda:ListFunctions` with `aws:RequestedRegion=eu-west-1` and
`apigateway:GET` on the regional `/apis` collection. The Lambda list action does
not support resource-level permissions, so its unavoidable `Resource: "*"` is
isolated in a statement containing no other action and constrained by region.
Do not attach AWS managed read-only policies.

Return only resource names, type and a small allowlist of runtime/protocol state.
Discard ARNs, account IDs, API IDs, endpoints, environment variables, tags,
pagination tokens and raw SDK errors. Partial failures are sanitized and all
request/resource counters are explicit. The deployed closed state is unchanged
until a separate IAM and DEV deployment approval is granted.

## D-024 - One fresh Inspector discovery process after OAuth lifecycle failure

Inspector 2.4.0 can report `StreamableHTTPClientTransport already started` after
completing OAuth. Its installed CLI reconnects after interactive authorization;
the installed transport rejects a second start, even after close. This behavior
was reproduced offline. Keep the pinned Inspector and recover only this exact
error by starting one new CLI process for `tools/list` with `--stored-auth-only`.

Require matching issuer, resource audience, scope, client, access-token type and
at least 30 seconds of remaining token validity before recovery. These decoded
claims are a local recovery filter, not signature verification; API Gateway and
Lambda remain the authorization boundary. Refuse recovery after 180 elapsed
seconds measured before window opening. Keep the existing five-minute schedule
and 15-request tripwire, and never retry tool execution. A failure of the fresh
discovery process closes the window via the existing finally block.

## D-025 - Persistent single-use confirmation with zero-fixed-cost secrets

Use a conditional DynamoDB update for remote confirmation consumption. The
record contains only a token digest, caller fingerprint, action, payload digest,
expiry and consumed flag. Keep consumed records until TTL cleanup so replays can
be distinguished, and check expiry in the condition because TTL deletion is
asynchronous. Configure on-demand billing with maximum read and write throughput
of one read and two write request units per second, and create the table only
when external integrations or the Cost Explorer quota are explicitly enabled.

Store Telegram and Trello configuration together in one Parameter Store Standard
SecureString encrypted by the AWS-managed `aws/ssm` key. Fetch it only after
confirmation consumption, with one SDK attempt. Do not use Secrets Manager or a
customer-managed KMS key because both add fixed monthly cost for this scale.

Each provider adapter makes one HTTPS POST, has a four-second timeout and never
retries. An ambiguous timeout consumes the confirmation and requires a new user
preview and confirmation. Provider credentials and destination identifiers are
kept behind stable aliases and no raw response or exception crosses the adapter.

## D-026 - Valid SSM namespace and DPAPI credential handoff

AWS reserves parameter names whose first path segment begins with `aws` or `ssm`.
Use `/portfolio/aws-remote-mcp/<environment>/...` for project parameters instead
of `/aws-remote-mcp/...`, and enforce the same namespace in SAM constraints,
runtime validation, tests and operational scripts.

When a human must hand credentials to local automation, capture them with hidden
PowerShell prompts and protect the handoff using Windows DPAPI for the current
user. Store it outside the repository with a current-user-only ACL. Preserve the
encrypted handoff across validation failures to avoid repeated secret entry, but
overwrite and delete it immediately after AWS confirms SecureString creation.
Never print, log or commit the plaintext or encrypted payload.

## D-027 - Escape DynamoDB attribute names in production expressions

DynamoDB expression keywords can reject an otherwise valid conditional update
at runtime even when local fakes pass. Treat every application-owned attribute
used in an update or condition as potentially reserved and map it through
`ExpressionAttributeNames`. The first live confirmation correctly failed before
the provider boundary because `consumed` was unescaped; the record stayed
unconsumed and no Telegram request was attempted. The corrected expression uses
`#consumed` for both update and condition, with a regression assertion on the
generated request.

## D-028 - Long-lived Trello credential behind a fixed runtime destination

Use a long-lived Trello user token for unattended DEV integration instead of a
monthly manual rotation that silently disables the portfolio service. Trello
does not offer token restriction to one board or list, so compensate by omitting
account-management scope, keeping the token only in the Standard SecureString,
granting Lambda access to that exact parameter and mapping the MCP tool solely to
the fixed `portfolio/inbox` list identifier. Never accept a provider destination
or credential from tool arguments. Revoke and replace the token immediately if
disclosure is suspected.

## D-029 - Allowlisted best-effort audit records after tool completion

Emit one structured record after each MCP tool result using a builder whose API
does not accept arguments, result data or confirmation metadata. Record only the
environment, Lambda request ID, caller fingerprint, allowlisted tool name,
normalized status, issue codes and bounded counters. Use the existing
seven-day-retention Lambda log group rather than adding a persistent audit
service.

Audit emission is best effort and must not replace a completed tool result. In
particular, a logging failure after a provider write cannot create an ambiguous
client error that encourages a duplicate retry. DynamoDB confirmation state is
the authoritative single-use control; logs are evidence, not a transaction.

## D-030 - Empty, isolated and closed initial PROD

Promote the reviewed source through `main`, then create separate PROD application
and Cognito stacks. Do not clone the DEV user, provider SecureString,
confirmation table or external destinations. PROD begins with integrations off,
zero Cognito users, API Gateway disabled and Lambda reserved concurrency zero.

The initial API identifier and Cognito resource URI form a deployment dependency
cycle. Resolve it with a closed bootstrap application stack, create the bound
PROD authorization stack, then immediately replace the bootstrap issuer and
audience with the PROD values. Because both execution gates are fixed closed in
the template, the intermediate configuration cannot process requests.

## D-031 - Multi-client OAuth through WorkOS AuthKit

The portfolio target is a public remote MCP that a user can add to different AI
clients, not a single-company installation and not an Inspector-specific demo.
Supersede D-018 only for future client onboarding: retain its Cognito deployment
as historical validation infrastructure, while selecting WorkOS AuthKit for the
next DEV profile.

Use WorkOS because its MCP authorization service natively supports the current
Client ID Metadata Document flow and deprecated DCR fallback, authorization code
with S256 PKCE, hosted user authentication, exact resource indicators and JWT
verification. Its staging environment adds no provider charge or AWS resource,
and the published AuthKit allowance is far above portfolio traffic. Do not add a
custom registration shim or store a WorkOS management key in the MCP runtime.

Make the AWS resource server provider-neutral. Configure JWT issuer, OAuth
authorization-server issuer, exact MCP audience and one required scope as
deployment inputs. WorkOS uses `openid`; the legacy Cognito profile retains its
resource-bound `/use` scope. Require `token_use=access` when a provider emits the
claim, but do not require this Cognito-specific claim from other issuers. Exact
issuer, audience, expiry, subject and scope remain mandatory at API Gateway and
are checked again at Lambda before bearer removal.

First configure WorkOS staging and deploy only to closed DEV. Validate provider
metadata before opening, then test Claude, Cursor and Codex-compatible clients in
separate five-minute windows with the existing concurrency, throttling, request
alarm and automatic shutdown controls. PROD remains unchanged until those tests
pass and an always-on cost posture is separately reviewed.

## D-032 - Opt-in Resource Explorer search through an existing view

Support Resource Explorer as a separate read-only search source, not as part of
the fixed Lambda/API Gateway inventory operation. Keep it disabled when the
`ResourceExplorerViewArn` deployment parameter is empty. Enabling it requires
the exact ARN of a pre-existing view in `eu-west-1`; callers cannot choose a
view or region.

Grant only `resource-explorer-2:Search` on that exact view ARN and constrain the
request to `eu-west-1` and `resource-explorer-2:Operation=Search` (the IAM action
also maps to the separate `ListResources` API operation). Do not create
indexes, views or service-linked roles, grant Resource Explorer managed
policies, or activate/configure the service as part of this project. Resource
Explorer has no additional search charge; the
existing API Gateway and Lambda invocation costs and closed-by-default controls
remain unchanged. Cost Explorer remains excluded.

Treat search results as eventually consistent and incomplete: coverage depends
on supported resource types, the selected view's filters and pre-existing
index/aggregator configuration. Do not present Resource Explorer as a universal
or authoritative account inventory. The Search API reference lists `Search` as
the minimum operation permission, though AWS's troubleshooting guide also names
`GetView`; keep `GetView` absent until a separately approved closed DEV
validation demonstrates it is necessary, then scope any required permission to
the same exact view.

## D-033 - Cost Explorer as a separately confirmed paid read

Expose Cost Explorer only when `EnableCostExplorer=true`; default it to false
for DEV and PROD. When false, hide the MCP tools, omit the API permission and
make no Cost Explorer call. When true, grant only `ce:GetCostAndUsage` on the
account's exact primary billing view ARN and pass that same ARN in the request.
Do not grant Cost Explorer wildcard or additional billing actions. The account-
level service activation remains outside this template and must never be
performed automatically.

Each confirmed execution is single-use and may issue at most one SDK request for
one result page, with retries and pagination disabled. Each page costs $0.01.
Before the API call, atomically consume one of three global UTC-month slots in
the confirmation table; failures consume their slot, exhausted or unavailable
quota fails closed, and no caller can reset it. This limits Cost Explorer calls
originating from this MCP to $0.03 per month while the table remains intact.
Current-month data is delayed, typically by about a day, so the tool is not a
real-time spend monitor or an AWS-account-wide hard budget cap.

Use the existing confirmation table when either external integrations or Cost
Explorer is enabled, without enabling Telegram or Trello when only Cost
Explorer is on. If both features are later disabled, the conditional table is
deleted with the application stack; no Cost Explorer service resource is
created by the template. Cost Explorer remains false in PROD.
