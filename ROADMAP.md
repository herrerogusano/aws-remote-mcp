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
- Completed first-login password replacement and fail-closed local TOTP
  enrollment tooling.
- Validation identity verified with software-token MFA enabled.
- Cognito JWT authorizer and public protected-resource metadata deployed with the
  API closed by default.
- Bounded remote MCP Inspector validation through authorization code, PKCE and
  TOTP, followed by independently verified cleanup.
- Least-privilege AWS inventory adapter and exact read IAM deployed to closed
  DEV for Lambda and API Gateway v2, validated remotely on 2026-09-07 with two
  reads, ten resources and zero writes, followed by verified cleanup.
- Telegram and Trello adapters with one-attempt writes, persistent single-use
  confirmation, conditional least-privilege infrastructure and a
  zero-fixed-cost Parameter Store credential design.
- Closed-API DEV validation of one confirmed Telegram message and one confirmed
  Trello card, followed by independent shutdown verification.
- Sanitized structured audit records with exact-schema regression coverage,
  deployed and verified in CloudWatch without additional provider writes.
- Complete Telegram and Trello transport-failure matrix and conservative final
  validation-window cost review.
- Reviewed manual promotion to `main` and an isolated, empty PROD deployment
  with independent Cognito authorization and both execution gates closed.
- WorkOS AuthKit onboarding from Codex through CIMD, PKCE and OAuth, followed by
  successful remote diagnostics and bounded AWS inventory with zero writes.
- Opt-in Resource Explorer search implemented offline with one-page bounds,
  sanitized identifiers and an exact-view least-privilege IAM contract.

## Next milestones

The server and Codex client validation are complete. The next portfolio steps
remain deliberately gated:

1. Configure one pre-existing Resource Explorer view and validate the new search
   in closed DEV before considering deployment to PROD.
2. Add a separately confirmed, single-page Cost Explorer query with its explicit
   `$0.01` API cost only after Resource Explorer validation.
3. Optionally validate onboarding from Claude or another compatible client.
4. Decide whether a public always-on PROD demonstration is justified after its
   abuse and cost controls are tested in DEV.
5. Consider GitHub OIDC delivery and a recorded demonstration afterward.

## Success criteria

- A real compatible MCP client connects remotely with secure authorization.
- AWS inventory is bounded, normalized and least privilege.
- Telegram/Trello writes cannot occur without scoped user confirmation.
- DEV and PROD are isolated and reproducibly deployed.
- CI/CD, audit logs, throttling, rollback and cost controls are demonstrated.
- Public documentation explains the design, trade-offs and evidence clearly.
