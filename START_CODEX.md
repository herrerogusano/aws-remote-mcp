# START_CODEX.md

Prepare and execute Exercise 5 autonomously.

## Repository

Create a new independent local repository named `aws-remote-mcp` alongside the user's existing portfolio/AWS repositories if that location can be inferred safely. Never overwrite an existing repository.

If `aws-remote-mcp` already exists, inspect it first and continue only if it is clearly this exercise.

## Planning files

Expected at repo root:

```text
aws-remote-mcp/
├── AGENTS.md
├── PLAN.md
├── START_CODEX.md
└── docs/
    └── plan/
        ├── GATES.md
        ├── PROGRESS.md
        ├── REFERENCES.md
        └── phases/
            ├── 00-bootstrap-ci.md
            ├── 01-core-tools.md
            ├── 02-streamable-http.md
            ├── 03-auth-contract.md
            ├── 04-aws-remote-deploy.md
            ├── 05-aws-auth.md
            ├── 06-aws-resource-tool.md
            ├── 07-telegram-tool.md
            ├── 08-trello-tool.md
            ├── 09-reliability-observability.md
            ├── 10-security-cost.md
            ├── 11-dev-prod-manual-release.md
            ├── 12-cicd.md
            └── 13-demo-closeout.md
```

If you were given the planning ZIP, extract its CONTENTS directly into the repository root. Do not create a nested planning folder inside the repo.

## Read before acting

Read completely:

1. `AGENTS.md`
2. `PLAN.md`
3. `docs/plan/GATES.md`
4. `docs/plan/PROGRESS.md`
5. `docs/plan/REFERENCES.md`
6. all phase files

Then identify the first incomplete phase.

## Prior projects

Locate previous AWS exercise repositories if available. Especially inspect `aws-resource-mcp` as a design reference for inventory normalization, Boto3 clients, operation safety registry, cost policy, ephemeral consent, counters and partial failures.

DO NOT import it as a runtime dependency.

## Git + GitHub bootstrap

If needed:

- initialize Git;
- default branch `main`;
- make initial planning/bootstrap commit;
- use the user's existing authenticated GitHub environment to create remote repo `aws-remote-mcp` and configure `origin`.

Do not create new long-lived GitHub tokens if existing auth works.

If GitHub authentication is unavailable, continue local work until remote Git is necessary, then stop and explain what is missing.

## Autonomous execution

After bootstrap, immediately start the first incomplete phase and follow `AGENTS.md`.

Do not pause after each phase simply to announce completion. Continue until a gate requires explicit authorization.

Unless a gate applies, you may autonomously create branches, edit code, add dependencies/tests, update docs, commit, push, open PRs, inspect/fix CI, merge green PRs and begin the next phase.

## Gates

Stop before any action listed in `docs/plan/GATES.md`.

At a gate report:

```text
GATE: <name>

Current phase:
...

What is already prepared:
...

Critical action:
...

AWS/external resources affected:
...

IAM/auth changes:
...

Secrets involved:
...

Estimated cost/risk:
...

What happens after approval:
...

Rollback:
...
```

Then wait.

## CI

CI exists from Phase 0 and grows with the codebase. Normal CI must not require live AWS, Telegram, Trello, real OAuth login or paid calls.

## CD

Do not activate CD before its planned phase. After CD is active, a merge can deploy automatically, so gated deployable changes must stop before merge.

## First response

Before editing, respond briefly with:

- where the repository will live;
- whether `aws-resource-mcp` was found;
- whether all planning files were found;
- first pending phase;
- Git/GitHub availability;
- immediate blockers.

If there is no blocker and no gate, continue automatically after that summary.
