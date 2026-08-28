# Phase 7 — Telegram side-effect tool

## Goal
Add Telegram without giving the model unrestricted write authority.

## Gate
**Gate D applies before real credentials or first send.**

## Flow
```text
MCP caller
→ prepare Telegram action
→ normalized preview
→ ephemeral confirmation token
→ execute confirmed action
→ Telegram Bot API
```

## Work before gate
1. Implement Telegram adapter + fake.
2. Prefer configured/allowlisted destination; arbitrary tool input must not select unrestricted chats.
3. Validate message length/content format.
4. Confirmation binds caller, destination policy, exact message digest, expiry and one use.
5. Max one real send per confirmed execution.
6. No automatic retry after ambiguous failure.
7. Explicit HTTP timeout.
8. Never log credential-bearing Telegram URL.
9. Evaluate current secret storage/pricing.
10. Prepare exact Lambda secret-read IAM.
11. Test preview, success, expiry, caller mismatch, payload change, replay, HTTP errors/timeouts and secret leakage.
12. Present exact Gate D test message.

## After approval
Store real credential in approved secret store, deploy, send exactly one approved test message and confirm sanitized logs.

## Done
Telegram works only via scoped confirmation.
