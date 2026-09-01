# AWS Remote MCP roadmap

## Vision

Build a production-shaped remote MCP server that demonstrates secure serverless
architecture, least-privilege AWS access, controlled third-party side effects,
modern authorization and reproducible DEV/PROD delivery.

## Architecture

```text
MCP client
  -> HTTPS / Streamable HTTP
  -> API Gateway authorization and throttling
  -> AWS Lambda
  -> transport-independent tool services
  -> AWS APIs / Telegram / Trello
```

## Delivered

- Reproducible Python 3.13 + uv project and offline CI.
- Fail-closed AWS operation registry, bounded results and normalized errors.
- Scoped, expiring, single-use confirmation for external writes.
- Official stateless MCP Streamable HTTP application and local transport guards.
- OAuth resource-server contract with offline JWT verification tests.
- Lambda/API Gateway v2 adaptation and closed-by-default DEV infrastructure.
- Cost guardrails, temporary validation window and automatic shutdown path.
- Verified closed DEV deployment in `eu-west-1`.
- Three-call synthetic Lambda validation with the API kept disabled.
- Administrator-only Cognito validation identity with suppressed messaging.

## Next milestones

1. Complete the validation identity's first-login password change and TOTP
   enrollment without opening the API.
2. Replace temporary IAM with JWT authorization and validate MCP Inspector in a
   separately approved bounded window.
3. Add least-privilege AWS inventory collectors.
4. Add confirmed Telegram and Trello actions with separate credentials.
5. Complete structured audit logging, fault tests and cost review.
6. Prove manual DEV/PROD promotion, then add GitHub OIDC delivery.
7. Publish architecture, threat model, demo and operating runbooks.

## Success criteria

- A real compatible MCP client connects remotely with secure authorization.
- AWS inventory is bounded, normalized and least privilege.
- Telegram/Trello writes cannot occur without scoped user confirmation.
- DEV and PROD are isolated and reproducibly deployed.
- CI/CD, audit logs, throttling, rollback and cost controls are demonstrated.
- Public documentation explains the design, trade-offs and evidence clearly.
