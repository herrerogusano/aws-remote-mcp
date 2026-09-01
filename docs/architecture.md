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

The DEV runtime exists in `eu-west-1` and remains disabled outside bounded test
windows. Lambda and API Gateway remain the target unless current MCP protocol
behavior proves them incompatible; changing compute requires a documented
architecture review.

## Delivery model

```text
feature branch -> pull request -> develop -> DEV
develop -> promotion pull request -> main -> PROD
```

CI has no live integrations. CD is deferred until manual DEV and PROD releases
are stable and its deployment identity and rollback have been reviewed.

## Application boundaries

The core owns a central AWS operation registry, normalized results, cost
classifications, scoped consent, request counters, partial failures and safe
error translation without depending on another runtime package.

The remote design adds distinct caller authorization, Lambda IAM, downstream
credentials, per-tool structured audit records, and API Gateway throttling.

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

External writes use an opaque confirmation token backed by an in-memory record
that binds caller fingerprint, action, canonical payload digest, expiry, and
single use. Confirmation is consumed before calling a downstream adapter so an
ambiguous failure cannot be blindly retried. Durable/distributed confirmation
storage is intentionally deferred until the deployment architecture requires it.

Application results have a common status, data, warnings, sanitized errors,
counters, and optional confirmation metadata. Adapter output is size-bounded,
and every execution permits at most one external-write attempt.

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
`aws-remote-mcp/use`; confirmation is still independently required for writes.
