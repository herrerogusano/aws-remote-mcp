# OAuth/OIDC provider evaluation

Verified: 2026-08-28

## Decision

Use Amazon Cognito Plus as the first production-shaped authorization server and
the official MCP Inspector CLI/TUI as the pre-registered validation client.

This is a controlled-client profile, not a claim of universal zero-configuration
MCP compatibility. Cognito doesn't advertise Client ID Metadata Document (CIMD)
or Dynamic Client Registration (DCR) support. The Inspector explicitly accepts a
static client ID and documents the exact native callback URI used here.

## Selected flow

```text
MCP Inspector CLI/TUI
  -> protected-resource metadata discovery
  -> Cognito OIDC discovery
  -> pre-registered public client
  -> authorization code + S256 PKCE + resource indicator
  -> 5-minute audience-bound access token
  -> API Gateway JWT authorizer + required scope
  -> MCP Lambda caller normalization
```

The resource URI is the exact deployed MCP endpoint. Cognito receives it in the
OAuth `resource` parameter and places it in the access-token `aud` claim. The
resource-server identifier is the same URI, so the custom scope is
`<MCP resource URI>/use`. API Gateway must require both the
Cognito issuer/audience and this scope so an ID token cannot satisfy the route.

## Cost and abuse posture

- Cognito Plus has no free tier and costs $0.02 per direct/social MAU. With
  administrator-only creation and a one-user project policy, this is bounded to
  $0.02 in each month that the user is active; the empty pool costs $0.
- Self-registration is disabled; only an administrator can create the single
  validation user.
- No SMS, email OTP, custom domain, WAF, Lambda trigger or M2M client is
  configured. Plus threat protection is enforced without log export.
- The public client has no secret. It uses one exact loopback callback and PKCE.
- Access and ID tokens expire after five minutes. The one-day refresh token
  rotates with no grace reuse period and supports revocation.
- TOTP MFA is mandatory and doesn't create per-message charges.

AWS doesn't provide a hard Cognito spending cap. Restricting creation to an
administrator and the project to one user bounds the MAU charge, while excluding
message-based and request-priced features removes per-attempt costs. The
existing account budget remains an independent warning.

## Alternatives considered

| Provider | MCP registration | Advantages | Reason not selected first |
| --- | --- | --- | --- |
| Cognito | Pre-registration | AWS-native, PKCE, resource binding, short JWTs, enforced threat protection | Controlled clients only; CIMD/DCR absent |
| Descope | CIMD, DCR, pre-registration | Purpose-built MCP authorization and consent | External control plane and management credential |
| Stytch | CIMD/DCR and pre-registration | Full Connected Apps support and free 10k MAU | Requires an additional hosted consent application |
| WorkOS | CIMD/DCR | Managed MCP-capable authorization and large free AuthKit tier | External account and production billing setup |

If a future target client cannot accept a static client ID, Cognito must not be
wrapped with a custom registration endpoint. Re-evaluate a provider with native
CIMD before changing the resource server.

## Deployment boundary

`auth-template.yaml` is deliberately separate from the deployed closed app
stack. The auth stack was deployed on 2026-08-28 with the prefix
`remote-mcp-dev-hg`. One administrator-created validation identity was added on
2026-09-01 with messaging suppressed and no contact attributes. It has no deploy
defaults for the globally unique domain or canonical MCP URI. Credential
activation and opening a remote test remain gated actions. The JWT authorizer is
deployed but the entire API endpoint remains disabled.

The Cognito prefix validator also rejects the service-reserved terms `aws`,
`amazon` and `cognito`, which aren't expressed by the API's basic character
pattern but are prohibited for hosted prefix domains.

## Primary sources

- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration
- https://github.com/modelcontextprotocol/inspector/blob/main/clients/cli/README.md
- https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints-oauth-grants.html
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html
- https://aws.amazon.com/cognito/pricing/
