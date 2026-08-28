# Phase 5 — AWS OAuth/OIDC authentication

## Goal
Protect the remote MCP endpoint with an AWS-hosted standards-based auth design.

## Gate
**Gate B applies before creating/enabling production auth infrastructure.**

## Preferred candidate
Evaluate current:

```text
Amazon Cognito
→ OAuth/OIDC access token
→ API Gateway JWT authorizer
→ Lambda/MCP
```

Do not assume client compatibility.

## Work before gate
1. Verify current MCP auth requirements and Cognito pricing.
2. Verify authorization-code + PKCE support.
3. Verify metadata/discovery compatibility.
4. Verify intended MCP client can use Cognito/static registered client if needed.
5. Decide minimal scopes/audience.
6. Prepare IaC for User Pool/app client/domain if selected, API Gateway JWT authorizer and protected routes.
7. Keep metadata discovery route public where required; `/mcp` protected.
8. Add config/template tests.
9. Present Gate B.

## After approval
Deploy and prove: no token denied, invalid token denied, valid token safe call succeeds, claims normalized/sanitized.

## Stop condition
If Cognito needs non-standard hacks for the target client, STOP and present alternatives rather than weakening the protocol.

## Done
Remote MCP requires an authorized caller.
