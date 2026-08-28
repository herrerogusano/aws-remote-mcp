# Gates — mandatory human approval points

A gate means: prepare everything safe, test it, show impact, and STOP before the critical action. Approval applies only to the described scope.

## Gate A — First real AWS deployment

Before first deployment creating remote MCP infrastructure.

Show:

- SAM/CloudFormation resources;
- region;
- IAM;
- API exposure/auth state;
- throttling;
- expected request pattern;
- current official pricing/free-tier facts;
- rollback/delete plan.

First deployment should expose only a safe skeleton/diagnostic capability, not real external-write tools.

## Gate B — Authentication infrastructure

Before creating/enabling Cognito or another production OAuth/OIDC design.

Show:

- current MCP auth requirements;
- selected authorization server;
- API Gateway authorizer model;
- protected resource metadata;
- OAuth flow;
- static vs dynamic client registration support;
- scopes and audience;
- cost;
- client-compatibility limitations.

If Cognito cannot interoperate cleanly with the target MCP client, stop and present alternatives rather than inventing protocol behavior.

## Gate C — Broader AWS read permissions

Before materially expanding Lambda IAM across many AWS services/regions.

Show exact API actions, operation classifications, services/regions, max requests, blocked billable/unknown calls and IAM diff. Do not use blanket `ReadOnlyAccess`.

## Gate D — First real Telegram configuration/send

Before storing real Telegram credentials, enabling real sending or performing first real send.

Show secret storage, IAM, confirmation design, destination handling, retry behavior, max sends, log sanitization, exact test message and rollback/disable switch.

## Gate E — First real Trello credential/card creation

Before storing Trello credentials, enabling create, or first real card.

Show credential mechanism, board/list allowlist, confirmation flow, exact card preview, retries, idempotency, max cards and secret/log safety.

## Gate F — New potentially billable persistent service

Before adding persistent/uncertain-cost resources not already approved, such as custom DynamoDB rate-limit store, WAF, NAT Gateway, custom domain/Route 53, paid CloudWatch extras, provisioned concurrency, unnecessary Secrets Manager migration, queues/datastores, etc.

Show current official pricing and why the simpler architecture is insufficient.

## Gate G — Production environment activation

Before creating/enabling a separate production stack or production side effects.

Show dev/prod resources, duplicated cost, secrets separation, endpoints, deployment flow and how dev cannot write to production targets.

## Gate H — CD activation

Before first point where `merge to main → automatic AWS deployment`.

Show workflows, OIDC role/trust, deployment IAM, branch restriction, required checks, environments, deployed scope, rollback and secret exposure check.

After approval, normal already-authorized deployments may proceed automatically. Future gated changes still stop before merge.

## Gate I — Destructive action

Always stop before deleting meaningful stacks/data/secrets/production resources/Trello content, bulk cleanup or auth replacement that could lock users out. Show exact targets and recovery options.

## Gate J — Architecture escape hatch

If Lambda + API Gateway cannot correctly support required current MCP transport/client behavior, stop before switching compute.

Reproduce incompatibility, cite current evidence, compare alternatives/cost/operations and propose the smallest viable change.
