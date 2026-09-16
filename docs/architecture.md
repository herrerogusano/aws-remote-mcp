# Architecture baseline

## Target runtime

```text
MCP client
  -> HTTPS / Streamable HTTP
  -> API Gateway HTTP API with JWT authorization and throttling
  -> AWS Lambda
  -> transport-independent tool services
  -> AWS APIs / Telegram / Trello
```

The DEV and PROD runtimes exist independently in `eu-west-1`. DEV remains
disabled outside bounded tests, and PROD has never been opened. Lambda and API
Gateway remain the target unless current MCP protocol
behavior proves them incompatible; changing compute requires a documented
architecture review.

## Delivery model

```text
feature branch -> pull request -> develop -> DEV
develop -> promotion pull request -> main -> PROD
```

DEV and PROD use separate application and authorization configurations. No user,
SecureString, confirmation record or provider destination is promoted between
them. PROD begins with external integrations disabled and both its endpoint and
compute independently closed.

CI has no live integrations. CD is deferred until manual DEV and PROD releases
are stable and its deployment identity and rollback have been reviewed.

## Application boundaries

The core owns a central AWS operation registry, normalized results, cost
classifications, scoped consent, request counters, partial failures and safe
error translation without depending on another runtime package.

The remote design adds distinct caller authorization, Lambda IAM, downstream
credentials, per-tool structured audit records, and API Gateway throttling.

Per-tool audit records use an explicit safe schema: request ID, pseudonymous
caller fingerprint, allowlisted tool name, normalized status, issue codes and
bounded counters. Arguments, result data, previews, confirmation metadata,
provider identifiers and error messages are structurally unavailable to the
audit builder. See `docs/structured-audit-logging.md`.

## Transport-independent core

```text
MCP adapter
  -> ToolService
  -> operation registry / confirmation guard / normalized models
  -> adapter protocols
  -> offline fakes now, reviewed real integrations later
```

The central registry allows automatic execution only for operations classified
as `free_verified_read`; missing operations fail as `unknown`. Other supported
classifications are `controlled_billable`, `write`, and `sensitive_read`.

External writes use an opaque confirmation token that binds caller fingerprint,
action, canonical payload digest, expiry, and single use. Local previews use an
in-memory store. The optional remote integration profile uses DynamoDB so prepare
and execute can occur in different Lambda invocations; one conditional update
atomically changes the record from unconsumed to consumed. Confirmation is
consumed before calling a downstream adapter, so an ambiguous failure cannot be
blindly retried. Only a SHA-256 token digest is stored.

Application results have a common status, data, warnings, sanitized errors,
counters, and optional confirmation metadata. Adapter output is size-bounded,
and every execution permits at most one external-write attempt.

## External integration boundary

The deployment profile is disabled by default. When explicitly enabled, it adds
two prepare tools and two execute tools for one fixed Telegram alias and one
fixed Trello board/list alias. The exact aliases are checked before confirmation;
provider identifiers are resolved only inside the adapter.

One Standard SecureString in Parameter Store contains both providers' bounded
configuration. The value is fetched and decrypted only after a confirmation has
been consumed. Telegram and Trello adapters then make exactly one HTTPS POST with
a four-second timeout and no retry. Credentials, destination identifiers, raw
provider responses and raw errors never enter tool results.

## AWS inventory boundary

The first real AWS adapter exposes one fixed operation, `aws.inventory.list`.
It makes exactly one non-paginated Lambda `ListFunctions` request and one
non-paginated API Gateway v2 `GetApis` request in `eu-west-1`, with ten results
per service and SDK retries disabled. The adapter accepts no caller arguments
and no arbitrary service or operation names.

Only names and a small allowlist of non-sensitive configuration fields cross the
adapter boundary. ARNs, account IDs, API IDs, endpoints, environment variables,
tags, pagination tokens and raw exceptions are discarded. One failed service
produces a sanitized partial result; two failed services produce a sanitized
error. Local development and CI inject a deterministic fake and make no AWS
requests.

An independent opt-in operation, `aws.resource_explorer.search`, searches only
one preconfigured Resource Explorer view. Callers can supply a bounded positive
query and a limit from 1 to 50, but cannot choose the view, request another SDK
operation or continue pagination. Each invocation makes exactly one `Search`
request. The adapter discards full ARNs, account IDs, properties, tags, view
metadata and pagination tokens; it returns only service, resource type, region
and a bounded resource identifier. An absent view fails before client creation.

The deployment never creates or modifies Resource Explorer indexes, views or
service-linked roles. Its conditional IAM statement grants only `Search` on one
exact existing view and distinguishes the `Search` API from `ListResources`.
Resource Explorer remains eventually consistent and non-authoritative, so an
empty result cannot prove that a resource does not exist.

## Local MCP transport

The application core is wrapped in the official MCP Python SDK 2.x ASGI app:

```text
official MCP client
  -> http://127.0.0.1:8000/mcp
  -> modern 2026-07-28 Streamable HTTP
  -> stateless JSON request/response
  -> thin MCP tools
  -> ToolService and offline fakes
```

The server binds only to loopback, validates Host and Origin, limits request
bodies to 64 KiB, and exposes no execute/send/create side-effect tools. The
official client contract is validated against a real localhost Uvicorn server.

The selected Lambda adapter is the official ASGI app behind Mangum and API
Gateway HTTP API v2. See `docs/lambda-compatibility-spike.md`; AWS Lambda Web
Adapter remains the fallback before considering a custom protocol bridge.

## Authorization boundary

The protected variant of the ASGI app uses the official SDK bearer middleware,
an injected token-verifier protocol and public RFC 9728 protected-resource
metadata. A challenge middleware adds the operation's authoritative scope to
401/403 `WWW-Authenticate` responses.

Validated token data becomes only `CallerContext(issuer, subject, scopes)` before
entering application services. The bearer token remains inside the HTTP auth
boundary and is not a downstream credential. The initial MCP access scope is
`<MCP resource URI>/use`; confirmation is still independently required for writes.

The resource server is provider-neutral: JWT issuer, OAuth authorization-server
issuer, exact audience and required scope are independent deployment inputs. The
legacy Cognito profile uses its resource-bound `/use` scope. The multi-client
profile uses WorkOS AuthKit, an exact MCP resource audience and `openid`, while
supporting both CIMD and DCR client registration outside AWS. Provider-specific
claims such as Cognito's `token_use` are checked when present but are not assumed
to exist in standards-compliant access tokens.
