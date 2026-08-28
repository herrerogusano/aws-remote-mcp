# AGENTS.md — Autonomous execution rules

## Project

Repository name: `aws-remote-mcp`

Exercise 5: **Remote MCP on AWS**.

Goal: evolve the local AWS MCP patterns learned in Exercise 2 into a remotely reachable, authenticated MCP server running on AWS, exposed over Streamable HTTP, with reusable tools for:

- querying AWS resources safely;
- sending a Telegram message through an explicitly controlled side-effect flow;
- creating a Trello card through an explicitly controlled side-effect flow.

The target architecture is intentionally serverless and cost-aware.

## Source of truth

Read these files before doing work:

1. `AGENTS.md`
2. `PLAN.md`
3. `docs/plan/GATES.md`
4. `docs/plan/PROGRESS.md`
5. the current phase file under `docs/plan/phases/`

When documents disagree, precedence is:

`GATES.md` > `AGENTS.md` > current phase > `PLAN.md` > other docs.

Never silently override a gate.

## Autonomous phase workflow

Unless a gate applies, you are authorized to perform the normal engineering workflow autonomously:

```text
read current phase
→ create branch
→ implement
→ test
→ fix failures
→ update docs
→ update PROGRESS.md
→ commit
→ push
→ create PR
→ inspect CI
→ fix CI if needed
→ merge when green
→ update local main
→ begin next phase
```

Do not ask for permission merely to create a branch, edit code, add tests, update docs, commit, push, open a PR, repair CI caused by your changes, merge a green non-gated PR, or start the next phase.

If branch protection requires human review, respect it. Never bypass repository protections.

## Branch naming

Use one branch per phase or coherent gated slice:

`phase/<NN>-<short-name>`

Examples: `phase/00-bootstrap-ci`, `phase/02-streamable-http`, `phase/07-telegram-tool`.

## Commit and PR policy

Use small understandable commits. Every phase should normally finish in a PR whose description includes objective, main changes, tests, security impact, AWS impact, cost impact, gate status and limitations.

If CI is red, do not merge.

Never commit secrets, generated credentials, `.env`, AWS profiles, auth tokens, Telegram tokens, Trello credentials, account IDs, or raw production responses.

## CI-first policy

CI starts in Phase 0 and grows with the project. Normal CI must never depend on live AWS, Telegram, Trello, real OAuth login, or paid services. Live tests must be explicitly marked and excluded from automatic CI.

## CD policy

CD is introduced only after manual deployments are stable.

Before CD is enabled, merging code to `main` must not mutate AWS.

After CD is enabled, remember that merging a deployable change can itself become an AWS-changing action. Therefore a PR that crosses a gate MUST stop before merge. Normal low-risk already-authorized changes may still progress autonomously.

## AWS region

Default region: `eu-west-1`.

Do not change region without a documented technical reason. Verify current regional availability before using a service or feature.

## Cost philosophy

Primary rule: **zero accidental costs**.

This does not mean every operation must be free. It means:

- known safe/free reads may run automatically;
- intentionally billable operations must be bounded and approved;
- unknown-cost operations are blocked until classified;
- no uncontrolled retries;
- no high-throughput resources by default;
- no provisioned capacity unless justified and approved;
- no Cost Explorer runtime calls by default;
- no WAF, NAT Gateway, provisioned concurrency or persistent-cost service merely for polish.

Prefer the smallest architecture that proves the concept.

## MCP protocol policy

Use the current official MCP specification and official Python MCP SDK as primary references.

For remote transport:

- prefer **Streamable HTTP**;
- do not build new work on legacy HTTP+SSE;
- favor a stateless/serverless-compatible request model;
- prefer JSON responses where they improve Lambda/API Gateway compatibility;
- preserve real MCP protocol semantics;
- validate `Origin` where required;
- respect protocol-version behavior;
- do not invent a custom “MCP-like REST API”.

## Serverless constraint

Target:

```text
MCP client
→ HTTPS
→ API Gateway
→ Lambda
→ MCP server/tool layer
```

Avoid ECS/Fargate/EC2 unless Lambda/API Gateway is proven technically unsuitable. If current protocol/client requirements make the target incompatible, stop at the architecture gate and show evidence before changing compute.

## Authentication policy

The final remote MCP must not be anonymous.

Use standards-based bearer-token authorization aligned as closely as practical with the current MCP HTTP authorization specification:

- OAuth/OIDC-based access tokens;
- protected-resource metadata;
- correct `401`/`403` semantics;
- token audience validation;
- no token passthrough;
- HTTPS only remotely.

Amazon Cognito + API Gateway JWT authorization is the preferred AWS-native candidate, but do not force it if current MCP-client interoperability proves inadequate. Any alternative auth architecture is a gate.

## No token passthrough

The token presented by an MCP client authenticates access to this MCP server. Never forward that bearer token to AWS APIs, Telegram, Trello or any downstream service. Downstream services use separate credentials.

## Runtime identities

Separate at least:

- MCP caller identity;
- Lambda execution role;
- API Gateway authorization;
- GitHub deployment identity;
- Telegram credential;
- Trello credential.

## AWS operations

Reuse design lessons from Exercise 2, but create no runtime dependency on it.

Keep a central operation registry/classification. At minimum distinguish:

- `free_verified_read`
- `controlled_billable`
- `write`
- `sensitive_read`
- `unknown`

Automatic AWS inspection is limited to operations classified as safe. Unknown or potentially billable reads must not silently run.

## Side effects

Telegram sends and Trello card creation are external side effects. Never let an LLM-triggered tool perform them with no explicit safeguard.

Use a two-step or confirmation-token pattern:

```text
prepare/preview
→ scoped short-lived confirmation
→ execute once
```

The confirmation must bind to caller identity, intended action, normalized payload/hash, expiry and single use. Never use a permanent global “writes enabled” flag as consent.

## Idempotency

For side-effect tools:

- prevent obvious duplicates within one invocation;
- support an idempotency key where useful;
- document that exactly-once delivery cannot be guaranteed across AWS + third-party APIs without a distributed transaction.

Do not claim exactly-once semantics.

## Secrets

Secrets live outside source control. Parameter Store SecureString is the initial low-cost candidate where appropriate, but re-evaluate current provider recommendations at implementation time.

Never expose secrets in source, committed IaC values, GitHub, logs, MCP results, errors or vault docs.

## Logging

Use structured logs with fields such as request ID, anonymized caller fingerprint, tool, status, duration, operation counts and confirmation state.

Never log bearer tokens, Telegram token/chat ID, Trello credentials, AWS credentials, credential-bearing URLs, raw Boto3 responses or full sensitive payloads.

## Rate limiting

Use bounded traffic. Prefer API Gateway stage/route throttling before custom stateful rate limiting. Treat throttling as a protective target, not an absolute security boundary.

## Retries

Retries are conservative. Do not blindly retry Telegram sends, Trello card creation or unknown-cost AWS operations. Safe reads may use bounded SDK retry behavior. A retry must not multiply an external side effect.

## Dev/prod

If two environments are introduced, keep them understandable: separate stacks/config references and no production side effects from dev by default. Do not duplicate persistent resources without cost review.

## External references

When current behavior matters, verify authoritative sources: MCP spec/SDK, AWS docs/pricing, Telegram Bot API, Atlassian/Trello API, GitHub/AWS OIDC docs.

## Gates

Read `docs/plan/GATES.md`. At a gate:

1. finish safe local preparation;
2. run tests;
3. prepare IaC/diff;
4. identify resources/permissions;
5. estimate cost;
6. explain decision;
7. stop before the critical action.

Do not continue until explicit approval.

## Progress tracking

`docs/plan/PROGRESS.md` is the persistent checkpoint. Update it after every meaningful milestone so a fresh session can reconstruct state from `AGENTS.md`, `PLAN.md`, `GATES.md`, and `PROGRESS.md`.

## Definition of autonomous

Autonomy means moving forward without unnecessary approval. It does not mean bypassing cost gates, inventing credentials, weakening auth, broadening IAM silently, merging gated infrastructure after CD, deleting user data, or creating chargeable resources because they are “standard”.
