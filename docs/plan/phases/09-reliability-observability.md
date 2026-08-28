# Phase 9 — Reliability, observability and throttling

## Goal
Make the remote service diagnosable and resistant to accidental traffic spikes without overengineering.

## Structured logging
Include request ID, tool, caller fingerprint (non-PII), status, duration, SDK request count, resource count, confirmation outcome and external-side-effect attempted/succeeded.

Never log secrets, tokens, raw sensitive payloads or raw Boto3 responses.

## API Gateway
Review/configure route-level throttling with conservative targets for a personal portfolio MCP. Document that API Gateway throttling is best-effort protection, not an absolute security quota.

## Lambda
Review timeout, memory, concurrency, cold start and remaining-time checks. Tool work must stop before the request budget is exhausted.

## Partial failures
- AWS inventory: one collector fails → partial result.
- Telegram/Trello: ambiguous write failure → no blind retry.

## Native metrics first
Use Lambda/API Gateway native metrics and logs. Evaluate only a minimal alarm set. If a potentially billable persistent monitoring resource is needed, apply Gate F.

Do not add custom metrics/dashboards by default.

## Health
A health/readiness mechanism may exist but must not leak inventory, secret existence or auth internals.

## Tests
Fault-inject time budget, AWS throttling, third-party timeout, API Gateway event variations, malformed claims and all request/result caps.

## Done
Failures are diagnosable from sanitized logs and all request paths are bounded.
