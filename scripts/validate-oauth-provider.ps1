[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^https://')]
    [string]$AuthorizationServer,
    [Parameter(Mandatory)]
    [ValidatePattern('^https://')]
    [string]$Resource,
    [ValidatePattern('^[A-Za-z0-9:/._-]+$')]
    [string]$RequiredScope = "openid"
)

$ErrorActionPreference = "Stop"
$server = $AuthorizationServer.TrimEnd('/')
$oauthMetadataUrl = "$server/.well-known/oauth-authorization-server"
$oidcMetadataUrl = "$server/.well-known/openid-configuration"

function Assert-HttpsEndpoint {
    param(
        [Parameter(Mandatory)][object]$Value,
        [Parameter(Mandatory)][string]$Name
    )

    $uri = $null
    if (-not [Uri]::TryCreate("$Value", [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne "https") {
        throw "OAuth metadata has an invalid HTTPS endpoint: $Name"
    }
}

try {
    $metadata = Invoke-RestMethod -Method Get -Uri $oauthMetadataUrl -TimeoutSec 10
    $oidcMetadata = Invoke-RestMethod -Method Get -Uri $oidcMetadataUrl -TimeoutSec 10
}
catch {
    throw "OAuth or OpenID authorization-server metadata could not be retrieved."
}

if ("$($metadata.issuer)".TrimEnd('/') -ne $server -or
    "$($oidcMetadata.issuer)".TrimEnd('/') -ne $server) {
    throw "OAuth metadata issuer does not match the configured server."
}
foreach ($endpoint in @("authorization_endpoint", "token_endpoint", "registration_endpoint")) {
    Assert-HttpsEndpoint -Value $metadata.$endpoint -Name $endpoint
}
Assert-HttpsEndpoint -Value $oidcMetadata.jwks_uri -Name "jwks_uri"
if (@($metadata.grant_types_supported) -notcontains "authorization_code" -or
    @($metadata.grant_types_supported) -notcontains "refresh_token" -or
    @($metadata.response_types_supported) -notcontains "code" -or
    @($metadata.code_challenge_methods_supported) -notcontains "S256" -or
    @($metadata.token_endpoint_auth_methods_supported) -notcontains "none" -or
    @($metadata.scopes_supported) -notcontains $RequiredScope) {
    throw "OAuth metadata lacks the required public-client, PKCE, refresh-token, or scope capability."
}

[pscustomobject]@{
    AuthorizationServer = $server
    Resource            = $Resource
    RequiredScope       = $RequiredScope
    AuthorizationCode   = $true
    PkceS256             = $true
    RefreshTokens        = $true
    PublicClients        = $true
    DcrAdvertised        = $true
}
