# Exercise 5 — AWS Remote MCP

## Goal

Build a production-shaped **remote Model Context Protocol server on AWS**.

This final portfolio exercise evolves Exercise 2 from local MCP over stdio into a remotely reachable service and combines concepts from the previous exercises:

- MCP;
- Python;
- AWS Lambda;
- API Gateway;
- IAM;
- Boto3;
- OAuth/OIDC/JWT authorization;
- secrets;
- CloudWatch;
- SAM/CloudFormation;
- CI/CD;
- GitHub OIDC;
- external APIs;
- cost controls;
- rate limiting;
- dev/prod deployment thinking.

The server should expose reusable tools for:

1. querying AWS resources safely;
2. sending a Telegram message through a controlled confirmation flow;
3. creating a Trello card through a controlled confirmation flow.

## Repository

`aws-remote-mcp`

Independent repository. Exercise 2 may be inspected as reference, but Exercise 5 must not import it as a runtime dependency.

## Target runtime architecture

```text
MCP Client
    |
    | HTTPS / Streamable HTTP
    v
API Gateway HTTP API
    |
    | JWT authorization
    v
Lambda
    |
    +---- MCP protocol/server
    |
    +---- AWS tool layer ------> AWS APIs via Boto3
    |
    +---- Telegram tool -------> Telegram Bot API
    |
    +---- Trello tool ---------> Trello REST API
    |
    +---- secret providers ----> Parameter Store / approved secret store
    |
    +---- structured logs -----> CloudWatch
```

Authentication candidate:

```text
User / MCP Client
       |
       v
OAuth/OIDC Authorization Server
(preferred AWS-native candidate: Cognito)
       |
       | access token
       v
API Gateway JWT authorizer
       |
       v
/mcp
```

Delivery:

```text
Developer
   ↓
GitHub PR
   ↓
CI
   ↓
manual merge
   ↓
main
   ↓
CD
   ↓
GitHub OIDC
   ↓
SAM / CloudFormation
   ↓
AWS
```

## Protocol decision

Remote MCP must use the current standard remote transport: **Streamable HTTP**.

Do not build new code around legacy HTTP+SSE. Because the target is Lambda/API Gateway, prefer a stateless/serverless-friendly MCP mode and JSON responses when supported by the current official SDK. Codex must verify current SDK behavior rather than freezing assumptions from this plan.

## AWS constraint

API Gateway HTTP APIs have a finite integration timeout. Therefore:

- tool execution must be bounded;
- inventory operations must not perform unbounded cross-region scans;
- no long-lived SSE dependency in the initial architecture;
- no background work hidden behind one request;
- operations likely to exceed the request budget must return bounded/partial results or be redesigned.

## Relationship to Exercise 2

Exercise 2:

```text
local MCP over stdio
→ user asks for AWS resources
→ Boto3
→ normalization
→ cost guard
→ consent
```

Exercise 5:

```text
remote MCP over HTTPS
→ authenticated caller
→ API Gateway/Lambda
→ same safety principles
→ reusable remote tools
```

Reuse principles, not runtime code dependencies. Reusable ideas include normalized AWS models, operation registry, cost classification, ephemeral consent, partial results, counters and sanitization.

## Development philosophy

- CI starts in Phase 0 and grows continuously.
- Deployment starts local, then controlled manual AWS deploys.
- CD comes only after manual deployment is stable.
- Zero accidental costs.
- Real capabilities are not anonymously exposed.
- Telegram/Trello writes require explicit scoped confirmation.

## Phase map

| Phase | Name | Main outcome |
|---|---|---|
| 0 | Bootstrap + CI | Repo, Python/uv, test/lint/type CI from day one |
| 1 | Core tool architecture | Transport-independent services and safety contracts |
| 2 | Local Streamable HTTP | Real MCP over local Streamable HTTP |
| 3 | Authorization contract | OAuth/JWT resource-server behavior locally |
| 4 | First AWS remote deployment | Lambda + API Gateway safe skeleton |
| 5 | AWS authentication | Cognito/OIDC candidate + API Gateway JWT protection |
| 6 | AWS resource tool | Safe authenticated AWS inventory remotely |
| 7 | Telegram tool | Controlled remote Telegram side effect |
| 8 | Trello tool | Controlled remote Trello card creation |
| 9 | Reliability + observability + throttling | CloudWatch and bounded request behavior |
| 10 | Security + cost hardening | IAM, secrets, abuse boundaries, cost audit |
| 11 | Dev/prod + manual release | Stable manual deployment/environment model |
| 12 | CI/CD + GitHub OIDC | Automatic deployment after merge to main |
| 13 | Remote-client demo + closure | Real client, docs, demo, interview material |

## Intended tool catalog

### AWS

Preferred name: `listar_recursos_aws`

Capabilities may include region, bounded all-regions mode, service filters, normalized output, coverage status, resource count and SDK-request count. Unknown/potentially billable operations remain blocked.

### Telegram

Preferred controlled flow:

```text
prepare_telegram_message
→ confirmation token
→ send_telegram_message
```

### Trello

Preferred controlled flow:

```text
prepare_trello_card
→ confirmation token
→ create_trello_card
```

with board/list allowlisting.

## Non-goals

Do not turn this into a generic SaaS, admin UI, Kubernetes exercise, EC2 server, unrestricted AWS administrator MCP, remote shell, or autonomous AWS mutation bot. AWS tools remain read-oriented unless a separately approved extension says otherwise.

## Security model

```text
HTTPS
  ↓
OAuth/OIDC access token
  ↓
API Gateway authorization
  ↓
caller identity normalization
  ↓
MCP tool guard
  ↓
operation registry / confirmation guard
  ↓
least-privilege downstream credentials
```

A valid MCP token is not blanket authority to execute side effects.

## Rate and abuse controls

Initial controls:

- API Gateway route/stage throttling;
- Lambda reserved concurrency if appropriate;
- bounded payload size;
- bounded service/region selection;
- hard max SDK requests per tool call;
- max one external write per confirmed execution;
- no automatic retry for third-party writes.

Avoid custom DynamoDB rate limiting unless a concrete need appears.

## Observability

Use native Lambda/API Gateway metrics and CloudWatch logs first. Avoid custom metrics/dashboards unless they add clear value and pass cost review.

## Manual demo target

```text
remote MCP client
→ authenticate
→ discover tools
→ call AWS resource tool
→ receive normalized result
→ prepare Telegram/Trello side effect
→ obtain explicit confirmation
→ execute once
→ inspect CloudWatch correlation logs
```

## Interview story

By the end the user should be able to explain local vs remote MCP, stdio vs Streamable HTTP, Lambda/API Gateway, OAuth/OIDC/JWT, API Gateway vs Function URL, caller auth vs Lambda IAM, Boto3, least privilege, confirmation for model-controlled writes, rate limiting, retries/idempotency, CI/CD, GitHub OIDC and serverless/cost trade-offs.

## Definition of done

Exercise 5 is complete when:

- MCP is genuinely remote;
- transport is standards-aligned;
- endpoint is authenticated;
- AWS tool works remotely;
- Telegram and Trello tools are safely controlled;
- CI runs on PRs;
- deployment is reproducible;
- CD works after merge to main;
- secrets are outside the repo;
- IAM is least privilege;
- observability and throttling are usable;
- costs are bounded/documented;
- a real compatible MCP client can connect;
- README/demo/interview docs are complete.
