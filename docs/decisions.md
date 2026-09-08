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
of one request unit per second, and create the table only when the external
integration profile is explicitly enabled.

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
