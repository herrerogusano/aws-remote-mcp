# Portfolio demonstration

## Safe evidence tour

The project can be presented without opening AWS or making a provider write:

1. Show the architecture and trust boundaries in `docs/architecture.md` and
   `docs/threat-model.md`.
2. Run the local quality gates from the README and show all 170 tests passing.
3. Start the local MCP server and demonstrate `diagnostico` plus the deterministic
   inventory fixture. Local mode never contacts AWS.
4. Review `docs/direct-validation-evidence.md` for the authenticated remote,
   real inventory, confirmed provider and structured-audit results.
5. Show the live closed-state audit: API disabled, Lambda concurrency zero, no
   alarm and no active schedule.

This is the recommended portfolio path because it demonstrates the design and
its verified evidence without creating a temporary public surface.

## Controlled live demonstration

A live remote demonstration is optional. Follow `docs/deployment-runbook.md` and
use only the reviewed validation wrapper. It creates the independent shutdown
before enabling execution, limits the window to five minutes, requires Cognito
PKCE and TOTP, and closes immediately after the selected read-only calls.

Do not call Telegram or Trello execute tools merely to demonstrate connectivity.
Their confirmation flow and successful one-write evidence are already recorded.
Never extend a failing window; close it, diagnose offline and begin a new bounded
attempt only after review.

## Reviewer talking points

- Why the endpoint is disabled rather than merely authenticated while idle.
- Why confirmation is bound to the exact normalized action and consumed once.
- Why ambiguous provider outcomes are not retried.
- Why structured audit records omit payloads even when that reduces debugging
  detail.
- Why a cost envelope needs technical shutdown controls instead of relying on an
  AWS Budget notification.

