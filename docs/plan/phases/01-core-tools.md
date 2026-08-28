# Phase 1 — Core tool architecture

## Goal
Create transport-independent application/tool logic before exposing HTTP.

```text
MCP adapter
    ↓
tool handlers
    ↓
application services
    ↓
AWS / Telegram / Trello adapters
```

## Work
1. Inspect Exercise 2 `aws-resource-mcp`.
2. Reuse patterns, never runtime imports.
3. Create models for caller context, tool result, warnings/errors, counters and confirmation metadata.
4. Create AWS operation classification registry: `free_verified_read`, `controlled_billable`, `write`, `sensitive_read`, `unknown`.
5. Build confirmation guard abstraction.
6. Bind confirmations to caller, action, payload digest, expiry and one use.
7. Add fake AWS, Telegram and Trello adapters.
8. Build application tool handlers against fakes only.
9. Telegram/Trello remain preview-only.
10. Normalize all results and bound payload/result size.
11. Add unit tests for unknown-operation fail-closed, confirmation expiry/caller/payload/replay and max-one-write behavior.

## Important
No MCP transport yet. No AWS IAM. No permanent global writes-enabled switch.

## Done
Core is fully testable offline. Merge green PR and move to Phase 2.
