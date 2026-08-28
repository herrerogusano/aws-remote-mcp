# Phase 0 — Bootstrap + CI from day one

## Goal
Create the repository foundation and immediately establish a small CI safety net. No AWS resources are created.

## Work
1. Create Python project using `uv`.
2. Select a currently supported Python version compatible with AWS Lambda, current MCP Python SDK and tooling.
3. Create `src/` package layout.
4. Add pytest, lint/format and type checking.
5. Add `.gitignore` and minimal README.
6. Add initial PR CI.
7. CI runs locked dependency install, lint, format check, typing and unit tests.
8. Add trivial smoke test.
9. No live AWS or external APIs in tests.
10. Verify current official MCP Python SDK package/version but do not implement transport yet.
11. Document architecture assumptions and decisions.
12. Create/update vault Exercise 5 folder if available.

## CI lesson
This phase intentionally demonstrates that CI can start before the product is functional. Future phases extend it.

## Git
Branch: `phase/00-bootstrap-ci`.
Finish with PR/green CI/merge autonomously unless GitHub setup requires authentication.

## Done
Repo is reproducible, CI runs on PR, no secrets/AWS dependency, PROGRESS points to Phase 1.
