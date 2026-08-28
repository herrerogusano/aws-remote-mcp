# Authorization contract

Verified 2026-08-28 against the MCP 2026-07-28 authorization specification.

## Resource-server behavior

The remote MCP is an OAuth 2.1 resource server. The offline protected app proves:

- bearer tokens are read only from the `Authorization` header;
- missing, malformed, invalid, expired, wrong-issuer, wrong-audience, or ID tokens
  receive HTTP 401;
- a valid token missing `aws-remote-mcp/use` receives HTTP 403;
- 401/403 `WWW-Authenticate` challenges include the authoritative scope and
  protected-resource metadata URL;
- protected-resource metadata is public at the RFC 9728 path-specific URI and
  identifies the resource, authorization server and supported scope;
- validated claims normalize to issuer, subject, scopes and a non-PII caller
  fingerprint;
- inbound bearer tokens are never included in `CallerContext`, tool arguments,
  downstream adapter calls, results, or errors.

The single initial scope is `aws-remote-mcp/use`. It authorizes access to the MCP
resource but does not authorize a Telegram send or Trello create: those remain
separately bound to a short-lived, single-use confirmation.

## Offline verifier model

`OfflineJwtVerifier` accepts an explicit verification key and algorithm list and
validates signature, issuer, audience, expiry, subject and `token_use=access`.
It minimizes retained claims. It is a test model, not the planned production key
retrieval mechanism. `StaticTokenVerifier` is a deterministic fake for HTTP
middleware tests.

## Selected controlled-client profile

The selected first production-shaped profile is:

```text
MCP Inspector CLI/TUI with a pre-registered public client ID
  -> Cognito authorization code + PKCE
  -> audience-bound access token with aws-remote-mcp/use
  -> API Gateway HTTP API JWT authorizer
  -> Lambda caller normalization
```

API Gateway validates the JWT signature using issuer discovery, `iss`, `aud`
(or `client_id` only when `aud` is absent), expiry/time claims and route scopes.
The design must require a scope so ID tokens are not accepted accidentally.
Cognito's resource binding can place the requested MCP resource URI into access
token `aud` for user authorization-code flows.

The app client has no secret, uses only the authorization-code flow, and permits
the Inspector native callback `http://127.0.0.1:6276/oauth/callback`. Access
tokens last five minutes and must contain both the endpoint audience and
`aws-remote-mcp/use`.

## Client registration limitation

The current MCP priority is pre-registration, Client ID Metadata Documents, then
deprecated Dynamic Client Registration as a fallback. Cognito supports manually
created/pre-registered app clients and authorization code + PKCE, but does not
advertise Client ID Metadata Document support or a standard DCR registration
endpoint.

Therefore Cognito is compatible only with a target MCP client that can use a
pre-registered public client ID and exact callback URI. The official MCP
Inspector supports this configuration. If another target client requires CIMD
or DCR, compare authorization-server alternatives instead of inventing a
registration protocol or weakening authorization.

The configuration contract is prepared in `auth-template.yaml`; no authorization
resource or user has been created yet.

## Deployment boundary

This contract creates no authorization server and no AWS resource. The normal
local runner remains loopback-only and unprotected for development. The
separately constructed protected app is the executable contract for deployment.

## Sources

- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html
