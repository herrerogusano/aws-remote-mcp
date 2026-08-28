# Phase 8 — Trello card tool

## Goal
Add controlled Trello card creation.

## Gate
**Gate E applies before real credentials and first real card.**

## Flow
```text
MCP caller
→ prepare card
→ validate board/list allowlist
→ preview
→ ephemeral confirmation
→ create once
```

## Work before gate
1. Verify current official Atlassian/Trello auth guidance.
2. Implement Trello adapter + fake.
3. Configure allowlisted board/list/labels as appropriate.
4. Tool input may select only allowed destinations.
5. Validate title/description/labels/URLs; no attachments/checklists initially.
6. Confirmation binds exact normalized card payload.
7. Add idempotency key support if useful.
8. No automatic retry after ambiguous create.
9. Max one card per confirmed execution.
10. Explicit timeout and secret isolation.
11. Test preview, allowlist rejection, confirmation, replay, payload mutation, timeout/API errors and secret leakage.
12. Present Gate E with exact test-card preview.

## Non-goals
No delete/move/edit arbitrary cards or board creation.

## Done
Trello create works only through controlled confirmation.
