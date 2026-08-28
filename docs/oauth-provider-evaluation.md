# OAuth/OIDC provider evaluation

Verified: 2026-08-28

## Decision

Use Amazon Cognito Lite as the first production-shaped authorization server and
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
custom scope remains `aws-remote-mcp/use`. API Gateway must require both the
Cognito issuer/audience and this scope so an ID token cannot satisfy the route.

## Cost and abuse posture

- Cognito Lite and Essentials include 10,000 direct/social MAU per month in the
  indefinite free tier.
- Self-registration is disabled; only an administrator can create the single
  validation user.
- No SMS, email OTP, custom domain, WAF, Lambda trigger, M2M client, threat
  protection or Plus tier is configured.
- The public client has no secret. It uses one exact loopback callback and PKCE.
- Access and ID tokens expire after five minutes. The refresh token expires
  after one day and supports revocation. Rotation is unavailable in the Lite
  tier and is deliberately omitted to avoid a paid tier.
- TOTP MFA is mandatory and doesn't create per-message charges.

AWS doesn't provide a hard Cognito spending cap. Restricting the number of users
and excluding message-based and paid add-ons bounds the practical project path,
while the existing account budget remains an independent warning.

## Alternatives considered

| Provider | MCP registration | Advantages | Reason not selected first |
| --- | --- | --- | --- |
| Cognito | Pre-registration | AWS-native, PKCE, resource binding, short JWTs, free tier | Controlled clients only; CIMD/DCR absent |
| Descope | CIMD, DCR, pre-registration | Purpose-built MCP authorization and consent | External control plane and management credential |
| Stytch | CIMD/DCR and pre-registration | Full Connected Apps support and free 10k MAU | Requires an additional hosted consent application |
| WorkOS | CIMD/DCR | Managed MCP-capable authorization and large free AuthKit tier | External account and production billing setup |

If a future target client cannot accept a static client ID, Cognito must not be
wrapped with a custom registration endpoint. Re-evaluate a provider with native
CIMD before changing the resource server.

## Deployment boundary

`auth-template.yaml` is deliberately separate from the deployed closed app
stack. The auth stack was deployed on 2026-08-28 with the prefix
`remote-mcp-dev-hg` and zero users. It has no deploy defaults for the globally
unique domain or canonical MCP URI. User creation, API authorizer replacement
and opening a remote test remain gated actions.

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
