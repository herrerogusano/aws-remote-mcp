# Phase 13 — Remote-client demo, portfolio and closure

## Goal
Prove the remote MCP works from a real compatible client and close Exercise 5 as a portfolio project.

## Client compatibility
Verify current remote MCP support at implementation time.

Use:
1. MCP Inspector/official client for protocol proof;
2. at least one real user-facing MCP client supporting the deployed auth/transport.

Do not rely on old client docs.

## Demo flow
```text
remote client
→ authenticate
→ tools/list
→ listar_recursos_aws
→ normalized result
→ prepare Telegram message
→ show confirmation
→ execute approved send
→ prepare Trello card
→ show confirmation
→ execute approved create
→ inspect CloudWatch correlation logs
```

Use safe/limited AWS data.

## README
Cover:
- what it does;
- local vs remote MCP;
- architecture;
- auth flow;
- tools;
- side-effect safeguards;
- IAM;
- cost controls;
- throttling;
- observability;
- mandatory per-tool CloudWatch audit logging;
- basic API Gateway rate limiting;
- DEV/PROD branch and deployment model;
- CI/CD;
- local development;
- deployment;
- limitations;
- demo.

## Architecture diagrams
Runtime:
```text
MCP Client
→ Auth
→ API Gateway
→ Lambda
→ Tools
→ AWS / Telegram / Trello
```

Delivery:
```text
PR
→ CI
→ manual merge
→ CD
→ OIDC
→ SAM
→ CloudFormation
```

## Interview material
Prepare concise explanations for:
- stdio vs Streamable HTTP;
- API Gateway vs Function URL;
- Lambda vs EC2/Fargate;
- OAuth/OIDC/JWT;
- API Gateway JWT authorizer;
- caller token vs Lambda IAM role;
- Boto3;
- least privilege;
- confirmation for side effects;
- rate limiting;
- retries/idempotency;
- CI/CD;
- GitHub OIDC;
- serverless/cost trade-offs.

## Troubleshooting
Document 401/403, MCP protocol mismatch, API Gateway 429, Lambda timeout, AWS AccessDenied, Telegram/Trello failures and GitHub OIDC/CD failures.

## Cleanup
Remove dead code, obsolete TODOs, fake production docs, personal paths, unused IAM and build artifacts.

## Final validation
Run full CI suite, SAM validate/build, security/IAM/secret audits, safe remote MCP test and only controlled side-effect demo if still permitted.

## Definition of complete
Mark `Exercise 5 — Complete` only if remote endpoint/auth/tools/side-effect safety/CI/CD/cost/docs/demo all work.

Suggested final commit: `docs: finalize AWS remote MCP portfolio project`.
