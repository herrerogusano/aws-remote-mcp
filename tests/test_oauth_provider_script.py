"""Static safety checks for external OAuth metadata validation."""

from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1] / "scripts" / "validate-oauth-provider.ps1"
).read_text(encoding="utf-8")


def test_validator_requires_safe_mcp_oauth_capabilities() -> None:
    for required in (
        ".well-known/oauth-authorization-server",
        ".well-known/openid-configuration",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "registration_endpoint",
        "authorization_code",
        "refresh_token",
        "S256",
        "token_endpoint_auth_methods_supported",
        "scopes_supported",
    ):
        assert required in SCRIPT


def test_validator_has_no_secret_or_mutating_request() -> None:
    assert "-Method Get" in SCRIPT
    assert "api_key" not in SCRIPT.lower()
    assert "client_secret" not in SCRIPT.lower()
    assert "Invoke-WebRequest" not in SCRIPT
