# Multi-client OAuth runbook

## Target

Use WorkOS AuthKit as the OAuth 2.1 authorization server for the public portfolio
MCP. WorkOS handles user sign-up, login, consent, Client ID Metadata Documents
(CIMD), Dynamic Client Registration (DCR), PKCE and token issuance. AWS remains
the resource server and accepts only a JWT issued for the exact MCP URL.

The first integration uses a free WorkOS staging environment and the closed DEV
AWS stack. It creates no new AWS resource and stores no WorkOS API key in AWS or
the repository. PROD remains unchanged and closed.

## Security contract

```text
Claude / Cursor / Codex-compatible MCP client
  -> RFC 9728 protected-resource discovery
  -> WorkOS AuthKit authorization-server discovery
  -> CIMD, or DCR for older clients
  -> authorization code + S256 PKCE + user consent
  -> JWT with issuer, subject, exact MCP audience and `openid` scope
  -> API Gateway JWT verification and throttling
  -> Lambda claim normalization
  -> MCP tools
```

The application accepts a missing Cognito-specific `token_use` claim, but rejects
it when present with any value other than `access`. Signature verification,
issuer, exact resource audience, expiry and the configured scope remain enforced
by API Gateway. Lambda repeats issuer, audience, subject, optional token type and
scope checks before discarding the bearer header.

## Manual WorkOS staging setup

1. Create a WorkOS account and keep the environment in **Staging**.
2. Enable AuthKit hosted authentication and user sign-up.
3. Copy the AuthKit domain shown for the staging environment. It has the form
   `https://<project>.authkit.app`; this is the OAuth issuer and authorization
   server.
4. Under **Connect -> Configuration**, enable **Client ID Metadata Document**.
5. Enable **Dynamic Client Registration** for clients that have not adopted CIMD.
6. Read the closed DEV `McpEndpoint` CloudFormation output and add that exact URL
   as a WorkOS **Resource Indicator**.
7. Set that Resource Indicator as the default for clients that omit `resource`.

Do not create an API key for this integration. The MCP server validates public
JWT signatures through the issuer metadata and never calls a WorkOS management
API.

## Offline and metadata preflight

```powershell
$app = aws cloudformation describe-stacks `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --output json | ConvertFrom-Json
$mcpEndpoint = ($app.Stacks[0].Outputs |
  Where-Object OutputKey -eq 'McpEndpoint').OutputValue
$authServer = 'https://<project>.authkit.app'

.\scripts\validate-oauth-provider.ps1 `
  -AuthorizationServer $authServer `
  -Resource $mcpEndpoint `
  -RequiredScope openid
```

The validator performs only two public metadata GETs. It requires authorization
code, refresh token, S256 PKCE, public-client token exchange, the `openid` scope,
OIDC issuer/JWKS discovery and a DCR registration endpoint. It does not register
a client or send a credential.

## Closed DEV deployment

Build and deploy only after the WorkOS staging preflight passes:

```powershell
$buildDir = ".aws-sam/build-workos-$([guid]::NewGuid().ToString('N'))"

sam build --template-file template.yaml `
  --build-dir $buildDir `
  --beta-features

sam deploy `
  --template-file "$buildDir/template.yaml" `
  --stack-name aws-remote-mcp-dev `
  --region eu-west-1 `
  --resolve-s3 `
  --capabilities CAPABILITY_IAM `
  --parameter-overrides `
    Environment=dev `
    OAuthIssuer=$authServer `
    OAuthAuthorizationServer=$authServer `
    McpTokenAudience=$mcpEndpoint `
    McpRequiredScope=openid `
    EnableExternalIntegrations=true `
    IntegrationConfigParameterName=/portfolio/aws-remote-mcp/dev/integrations `
  --no-confirm-changeset `
  --no-fail-on-empty-changeset
```

This deployment must leave `DisableExecuteApiEndpoint=true` and Lambda reserved
concurrency at zero. It changes the JWT provider but does not open the service.

## Bounded client validation

Open a maximum five-minute window only after the closed deployment is audited:

```powershell
.\scripts\open-dev-window.ps1 `
  -AuthorizationProfile ExternalOAuth `
  -AuthorizationServer $authServer `
  -RequiredScope openid `
  -UseUnreservedConcurrency `
  -RequestThreshold 15
```

Connect a client using only `$mcpEndpoint`. A compatible client should discover
the authorization server and open AuthKit without asking the user for a client
ID or secret. Always close immediately after the test:

```powershell
.\scripts\close-dev-window.ps1
```

Validate one client at a time. Start with read-only discovery and
`diagnostico`; external writes remain subject to their separate, single-use
confirmation flow.

## Production boundary and cost

WorkOS staging is free. WorkOS currently documents AuthKit as free up to one
million monthly active users, but enabling its production environment requires
billing information. No production WorkOS environment, AWS deployment or public
always-on service is part of this runbook.

Primary references:

- https://workos.com/docs/authkit/mcp
- https://workos.com/docs/authkit/environments
- https://workos.com/pricing
- https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization

## DEV deployment evidence

The WorkOS staging profile was deployed to closed DEV on 2026-09-09. Public
provider metadata advertised authorization code, refresh tokens, S256 PKCE,
public clients, `openid`, JWKS and DCR. The CloudFormation change set modified no
resource through replacement and added or removed no resource.

Post-deployment control-plane reads confirmed:

- CloudFormation `UPDATE_COMPLETE`;
- API endpoint disabled;
- MCP Lambda reserved concurrency zero;
- JWT route scope exactly `openid`;
- issuer and authorization server exactly
  `https://possible-movie-92-staging.authkit.app`;
- audience exactly the DEV MCP endpoint;
- zero request alarms and zero automatic-close schedules.

No OAuth login, MCP request or external provider write occurred during the
closed deployment. Live client compatibility remains unverified.
