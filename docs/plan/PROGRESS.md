# Progress

## Exercise

Exercise 5 — AWS Remote MCP

Repository: `aws-remote-mcp`

Region: `eu-west-1`

## Current state

Repository bootstrapped with a reproducible Python 3.13 + uv project. Phase 0
quality checks pass locally and CI is configured for pull requests and pushes to
both long-lived branches. No AWS resources or external integrations exist.

## Phase status

- [x] Phase 0 — Bootstrap + CI
- [ ] Phase 1 — Core tool architecture
- [ ] Phase 2 — Local Streamable HTTP
- [ ] Phase 3 — Authorization contract
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

Phase 1 — Core tool architecture

## Approved gates

None.

## Pending gates

Gate A will be required before the first real AWS deployment.

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
format checking, lint, strict typing, source compilation and offline unit tests.

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

## Risks and limitations

- The current smoke test proves only the project foundation; protocol and runtime
  behavior begin in later phases.
- Lambda/API Gateway compatibility with MCP SDK 2.x Streamable HTTP remains a
  Phase 2 architecture decision.

## Next action

Start Phase 1 from `develop` after the Phase 0 PR is green and merged.

## Update instructions

After each phase update phase checkbox, active phase, resources, IAM/auth changes, gate approvals, CI/CD state, risks/limitations and next action.
