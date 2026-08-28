# Phase 6 — Authenticated AWS resource tool

## Goal
Bring the central Exercise 2 capability into the remote server safely.

## Tool
Preferred external name: `listar_recursos_aws`.

Preserve useful semantics where practical: region, bounded all-regions, service filters, normalized output, coverage status, resources detected and SDK requests used.

## Policy
Remote callers cannot override cost policy via arguments. Safe classified operations may run; unknown/potentially billable/sensitive/write operations are skipped or blocked.

## Gate
**Gate C applies before materially broadening Lambda IAM.**

## Work
1. Port collectors incrementally, starting with a bounded safe subset.
2. Re-evaluate each Boto3 operation using current behavior/pricing.
3. Keep a central operation registry.
4. Use bounded timeouts/retries.
5. Hard-limit regions, pages, SDK requests, services and returned resources.
6. Return partial results before timeout rather than scanning forever.
7. Never return raw Boto3 responses.
8. Keep runtime AWS writes at zero.
9. Test safe/blocked operations, permission errors, timeout, page/request/region/output caps.

## Done
Authenticated remote MCP client can safely query AWS resources.
