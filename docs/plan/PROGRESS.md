# Progress

## Exercise

Exercise 5 — AWS Remote MCP

Repository: `aws-remote-mcp`

Region: `eu-west-1`

## Current state

Phases 0-3 are merged into `develop`. The DEV-only SAM stack, Lambda adapter,
bounded infrastructure and deployment runbook for Phase 4 are prepared and pass
offline checks. Gate A is pending; no AWS deployment or external integration
has been performed.

## Phase status

- [x] Phase 0 — Bootstrap + CI
- [x] Phase 1 — Core tool architecture
- [x] Phase 2 — Local Streamable HTTP
- [x] Phase 3 — Authorization contract
- [ ] Phase 4 — First AWS remote deployment
- [ ] Phase 5 — AWS authentication
- [ ] Phase 6 — AWS resource tool
- [ ] Phase 7 — Telegram tool
- [ ] Phase 8 — Trello tool
- [ ] Phase 9 — Reliability, observability and throttling
- [ ] Phase 10 — Security and cost hardening
- [ ] Phase 11 — Dev/prod and stable manual release
- [ ] Phase 12 — CI/CD and GitHub OIDC
- [ ] Phase 13 — Remote-client demo and closeout

## Active phase

Phase 4 — First AWS remote deployment

## Approved gates

None.

## Pending gates

Gate A is pending before the first `sam deploy` to `eu-west-1`.

## Runtime resources

None assumed.

## External side effects

Disabled/not implemented.

## Environments

Required target model:

- `develop` → DEV stack
- `main` → PROD stack

Neither environment is assumed deployed yet.

## CI

Implemented in `.github/workflows/ci.yml`: locked dependency installation,
format checking, lint, strict typing, source compilation, SAM lint/build and
offline unit tests.

## CD

Not implemented.

Final required behavior:

- merge to `develop` → deploy DEV
- approved merge to `main` → deploy PROD

## Key decisions

- Python + uv.
- AWS region `eu-west-1`.
- Remote MCP uses current Streamable HTTP, not legacy HTTP+SSE.
- Target compute is Lambda + API Gateway unless proven incompatible.
- DEV/PROD separation is mandatory, not optional.
- Every tool invocation must be logged structurally to CloudWatch.
- Basic API Gateway throttling/rate limiting is mandatory.
- CI starts in Phase 0.
- CD follows stable manual deployment.
- Exercise 2 is reference only.
- Telegram/Trello writes require scoped confirmation.
- Python 3.13 is the single local/CI/future Lambda runtime target.
- The official MCP Python SDK is constrained to the current stable 2.x line.
- The transport-independent core uses adapter protocols and offline fakes.
- AWS operations fail closed unless registered as `free_verified_read`.
- External confirmations bind caller/action/payload/expiry and are single-use.
- Tool results, sanitized errors, counters and response-size limits are normalized.
- Local MCP uses current 2026-07-28 Streamable HTTP with stateless JSON responses.
- The local server binds to loopback and enforces Host, Origin and 64 KiB body limits.
- Mangum is the preferred Phase 4 ASGI/Lambda adapter spike; Lambda Web Adapter is
  the fallback before a custom bridge.
- The protected app publishes RFC 9728 metadata and enforces 401/403 bearer
  challenges with the `aws-remote-mcp/use` scope.
- Offline JWT verification proves signature, issuer, audience, expiry, access-token
  type and scope handling; callers retain only normalized identity fields.
- Cognito/API Gateway remains the preferred auth candidate only for clients that
  support a pre-registered OAuth client.
- Mangum uses a fresh stateless MCP ASGI app per Lambda event so the SDK lifespan
  remains valid across warm invocations.
- The Lambda artifact uses SAM's preview `python-uv` Linux x86_64 builder with a
  runtime-only lock under `src/`.
- The first DEV stack is bounded to 256 MB, 15 seconds, concurrency 2, API rate
  1/second with burst 2, and two seven-day log groups.

## Risks and limitations

- Real AWS, Telegram and Trello adapters are intentionally absent; only fakes
  exist in the core phase.
- Confirmation records are process-local until the deployment design establishes
  whether shared durable state is required.
- Phase 3 provides a protected app contract but intentionally creates no real
  authorization server or remotely exposed endpoint.
- Cognito does not provide current MCP CIMD or standard DCR registration; target
  client static-registration compatibility must be proven before Gate B.
- Mangum event translation, repeated lifecycle and package size are validated
  offline; cold/warm latency still requires the Gate A deployment.
- The Phase 4 endpoint has no authentication until Phase 5. Its only tools are
  diagnostic and synthetic, with throttling and concurrency bounds, but the URL
  will be publicly callable during this short-lived DEV validation.
- SAM's `python-uv` builder is currently an AWS preview feature.

## Next action

Open and validate the Phase 4 PR, then stop at Gate A. After explicit approval,
deploy only the DEV stack, run safe synthetic checks, inspect sanitized logs and
measure cold/warm latency.

## Update instructions

After each phase update phase checkbox, active phase, resources, IAM/auth changes, gate approvals, CI/CD state, risks/limitations and next action.
