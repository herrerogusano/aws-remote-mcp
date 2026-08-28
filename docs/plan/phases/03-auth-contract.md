# Phase 3 — Authorization contract locally

## Goal
Design/test remote MCP resource-server authorization before creating AWS auth resources.

A valid bearer token grants access to the MCP server; it does not automatically authorize Telegram/Trello side effects.

## Work
1. Verify current MCP HTTP authorization requirements.
2. Implement required protected-resource metadata behavior.
3. Create token-verifier abstraction and offline fake/JWT verifier.
4. Normalize caller identity from validated claims.
5. Define minimal scopes if useful.
6. Enforce missing/invalid/expired/wrong-audience token → 401 and insufficient scope → 403.
7. Implement correct `WWW-Authenticate` metadata behavior where required.
8. Never pass inbound bearer token downstream.
9. Test audience, issuer, scopes and token redaction.
10. Define Cognito + API Gateway JWT authorizer as preferred AWS candidate.
11. Investigate target-client compatibility with static registration vs Dynamic Client Registration.
12. Document limitations.

## Done
Authorization behavior is fully testable offline. Phase 4 will hit Gate A before deployment.
