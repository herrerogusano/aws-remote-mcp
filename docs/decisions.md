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
including Streamable HTTP. Transport code is deliberately deferred to Phase 2.

## D-003 - CI before runtime features

Every pull request to `develop` or `main` runs locked installation, formatting,
linting, strict typing, compilation, and unit tests. These checks have no live
AWS or external-service dependency.

## D-004 - Mandatory environment mapping

`develop` maps to DEV and `main` maps to PROD. Feature work branches from and
returns to `develop`; production changes arrive only through a promotion pull
request. No environment is deployed in Phase 0.

## D-005 - Transport-independent application core

MCP and HTTP adapters will call application services rather than contain tool
logic. The core depends only on adapter protocols, so all Phase 1 behavior is
tested with deterministic in-memory fakes and no network access.

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
