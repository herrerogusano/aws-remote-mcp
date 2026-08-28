# Phase 4 — First AWS remote deployment

## Goal
Deploy the smallest safe remote MCP skeleton to AWS.

## Gate
**Gate A applies before `sam deploy`.** Prepare everything first, then stop.

## Target
```text
Internet
  ↓ HTTPS
API Gateway HTTP API
  ↓
Lambda
  ↓
MCP Streamable HTTP adapter
```

Do not expose real broad AWS inventory, Telegram send or Trello create yet.

## Work before gate
1. Create SAM template for Lambda + HTTP API.
2. Route MCP endpoint methods correctly.
3. Use the Phase 2 Lambda adaptation decision.
4. Design around API Gateway timeout limits.
5. Bound Lambda timeout/memory/concurrency.
6. Finite log retention.
7. Execution role only baseline/log permissions.
8. No VPC/NAT/provisioned concurrency/custom domain.
9. Add conservative API route throttling.
10. Safe defaults.
11. Tests + SAM validate/build + IAM/template checks.
12. Present Gate A resources, cost and rollback.

## After approval
Deploy to `eu-west-1`, call only safe/synthetic MCP capability, confirm sanitized logs and measure basic latency. No side effects.

## Done
Safe remote MCP skeleton works. PROGRESS → Phase 5.


## Environment rules

- This phase deploys DEV only.
- Use a DEV API endpoint/stage/config.
- External Telegram/Trello real side effects remain disabled.
- Documentation and logs must identify `environment=dev`.
- Do not create PROD yet.
