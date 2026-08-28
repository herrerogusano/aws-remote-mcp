# Phase 11 — Required DEV/PROD environments + stable manual release

## Goal

Create and prove the final two-environment operating model before CD.

This exercise REQUIRES:

```text
develop
   ↓
DEV

main
   ↓
PROD
```

DEV/PROD is no longer an optional architecture decision.

## Required environment model

### DEV

Purpose:

- integration;
- remote MCP testing;
- auth testing;
- safe tool testing;
- controlled side-effect tests.

Preferred stack:

`aws-remote-mcp-dev`

### PROD

Purpose:

- stable portfolio endpoint;
- final real configuration;
- production-grade auth;
- final demo.

Preferred stack:

`aws-remote-mcp-prod`

PROD creation/activation requires **Gate G**.

## Separation

DEV and PROD must have separate where applicable:

- CloudFormation/SAM stack;
- API Gateway endpoint/stage/config;
- auth application/client configuration;
- secret parameter names;
- external side-effect destination policy;
- logs identifiable by environment.

They may share an AWS account and region.

Do not duplicate global resources unnecessarily.

## Side-effect safety

DEV must never accidentally use PROD destinations.

Preferred examples:

- Telegram disabled by default in DEV or configured to a dedicated test chat;
- Trello DEV allowlist points to a test board/list;
- production credentials/config are not readable by the DEV runtime role.

## Git mapping

Long-lived branches:

```text
develop → DEV
main    → PROD
```

Normal phase work:

```text
develop
  ↓
phase/*
  ↓ PR
develop
```

Production promotion:

```text
develop
  ↓ PR
main
```

No direct feature branch → `main` merge.

## Manual release path

Before CD, prove both deployment paths manually.

### DEV

```text
checkout develop
→ CI-equivalent checks
→ sam validate
→ sam build
→ change-set preview
→ sam deploy DEV
→ safe remote MCP smoke test
```

### PROD

After Gate G approval:

```text
promotion PR develop → main
→ CI
→ manual merge
→ sam validate/build
→ PROD change-set preview
→ manual sam deploy PROD
→ safe smoke test
```

Do not automatically send Telegram or create Trello cards as deployment smoke tests.

## Config

Use explicit environment configuration.

A missing environment value must fail safe rather than default silently to PROD.

## Cost review

Before Gate G show:

- incremental monthly cost of keeping both stacks;
- which resources are duplicated;
- which resources remain usage-only;
- whether any auth/custom-domain resource has persistent cost.

## Rollback

Document:

- CloudFormation rollback;
- code rollback;
- promotion rollback;
- how DEV can continue independently if PROD fails.

## CI evolution

CI must test:

- valid environment values;
- no DEV→PROD secret reference;
- no PROD stack name used in DEV config;
- no direct deploy-to-PROD defaults;
- environment-specific throttling exists;
- environment field is included in tool audit logs.

## Done

- DEV stack works manually.
- PROD stack exists and works after Gate G approval.
- branch/environment mapping is documented.
- DEV cannot reach PROD side-effect credentials/targets by mistake.
- manual deploy for both environments is reproducible.
- only then move to Phase 12.
