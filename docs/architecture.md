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

No runtime infrastructure exists in Phase 0. Lambda and API Gateway remain the
target unless Phase 2 proves that current MCP protocol behavior is incompatible;
changing compute would require Gate J.

## Delivery model

```text
phase branch -> pull request -> develop -> DEV
develop -> promotion pull request -> main -> PROD
```

CI starts without live integrations. CD is deferred until manual DEV and PROD
releases are stable and Gate H is approved.

## Boundaries carried forward from Exercise 2

Exercise 2 is a design reference, not a package dependency. Later phases will
adapt its central AWS operation registry, normalized results, cost classifications,
scoped consent, request counters, partial failures, and safe error translation.

The remote design adds distinct caller authorization, Lambda IAM, downstream
credentials, per-tool structured audit records, and API Gateway throttling.

## Transport-independent core

```text
future MCP adapter
  -> ToolService
  -> operation registry / confirmation guard / normalized models
  -> adapter protocols
  -> offline fakes now, real integrations in later phases
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

Phase 2 wraps the application core in the official MCP Python SDK 2.x ASGI app:

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
official client contract is exercised against a real localhost Uvicorn server.

For Phase 4, the preferred Lambda spike is the official ASGI app behind Mangum
and API Gateway HTTP API v2. See `docs/lambda-compatibility-spike.md`; AWS Lambda
Web Adapter is the fallback before considering a custom protocol bridge.
