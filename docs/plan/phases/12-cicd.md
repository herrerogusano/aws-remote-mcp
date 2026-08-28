# Phase 12 — CI/CD + GitHub OIDC for DEV and PROD

## Goal

Automate the stable two-environment release model.

Final behavior:

```text
phase/* → PR → develop
                ↓
               CI
                ↓
             merge
                ↓
       automatic DEV deploy
```

and:

```text
develop
   ↓ promotion PR
main
   ↓ CI
approved manual merge
   ↓
automatic PROD deploy
```

## Gate

**Gate H applies before activating either automatic AWS deployment path.**

## CI

PRs to both `develop` and `main` must run:

- locked dependency install;
- lint;
- format check;
- typing;
- unit tests;
- MCP protocol tests;
- auth tests;
- audit-logging tests;
- throttling/config tests;
- security/cost-policy tests;
- SAM validate/build.

Normal CI must not use:

- live AWS;
- live Telegram;
- live Trello;
- paid API calls.

## DEV CD

Trigger:

```text
push/merge to develop
```

Action:

```text
GitHub Actions
→ OIDC
→ temporary AWS credentials
→ SAM deploy aws-remote-mcp-dev
```

After Gate H activation, normal green phase PRs may merge to `develop` and deploy DEV autonomously unless that phase crosses another gate.

## PROD CD

Trigger:

```text
push/merge to main
```

Action:

```text
GitHub Actions
→ OIDC
→ temporary AWS credentials
→ SAM deploy aws-remote-mcp-prod
```

A promotion PR from `develop` to `main` is the only normal route to PROD.

The actual merge to `main` should remain an explicit production promotion decision unless the user later changes that policy.

Do not auto-merge production promotion PRs by default.

## GitHub OIDC

Do NOT store long-lived:

- AWS access key;
- AWS secret access key.

Use GitHub OIDC and temporary STS credentials.

Reuse an existing account-level GitHub OIDC provider if previous exercises already created one.

## Deployment roles

Prefer clear environment scoping.

Evaluate:

- one deployment role restricted by stack/environment conditions, or
- separate DEV and PROD deployment roles.

Choose the model that is easiest to explain while maintaining least privilege.

PROD trust must not allow arbitrary feature branches.

## Trust model

At minimum:

- exact repository;
- correct GitHub OIDC audience;
- branch/environment restriction;
- DEV role/path associated with `develop`;
- PROD role/path associated with `main`.

## Environments

Evaluate GitHub Environments:

- `dev`
- `prod`

Use them if they improve branch protection/config separation.

PROD may use an explicit environment protection/approval if compatible with the intended workflow.

## Deployment safety

Both workflows:

- serialized with `concurrency`;
- use explicit stack/environment names;
- do not use `sam deploy --guided`;
- handle empty changesets;
- never invoke MCP tools as a post-deploy side effect;
- never send Telegram;
- never create Trello cards;
- never broaden IAM outside the reviewed template.

## Required extra checks

CD must preserve the exercise EXTRA:

- tool audit logging remains enabled in both environments;
- API Gateway throttling remains configured in both environments.

A deployment that removes either requirement must fail validation.

## After CD activation

Remember:

```text
merge develop → AWS DEV mutation
merge main    → AWS PROD mutation
```

Therefore future gated changes stop before the relevant merge.

## Done

- PR CI protects both long-lived branches.
- `develop` deploys DEV automatically.
- an approved promotion merge to `main` deploys PROD automatically.
- no long-lived AWS credentials exist in GitHub.
- DEV/PROD remain isolated.
