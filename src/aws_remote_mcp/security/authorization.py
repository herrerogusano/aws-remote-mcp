"""Offline-testable OAuth resource-server authorization contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import time
from typing import Any

import jwt
from jwt import InvalidTokenError
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from aws_remote_mcp.core.models import CallerContext

MCP_USE_SCOPE_SUFFIX = "/use"


def mcp_use_scope(resource_server_url: str) -> str:
    """Return the only scope valid for the canonical MCP resource."""

    return f"{resource_server_url.rstrip('/')}{MCP_USE_SCOPE_SUFFIX}"


class CallerNormalizationError(RuntimeError):
    """Raised when validated token context lacks a stable caller identity."""


@dataclass(frozen=True, slots=True)
class AuthorizationConfig:
    issuer_url: str
    resource_server_url: str
    required_scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        expected = (mcp_use_scope(self.resource_server_url),)
        if not self.required_scopes:
            object.__setattr__(self, "required_scopes", expected)
        elif self.required_scopes != expected:
            raise ValueError("Required scope must be bound to the MCP resource URL.")

    def sdk_settings(self) -> AuthSettings:
        return AuthSettings(
            issuer_url=AnyHttpUrl(self.issuer_url),
            resource_server_url=AnyHttpUrl(self.resource_server_url),
            required_scopes=list(self.required_scopes),
        )

    @property
    def resource_metadata_url(self) -> str:
        return str(build_resource_metadata_url(AnyHttpUrl(self.resource_server_url)))


class StaticTokenVerifier:
    """Deterministic verifier for HTTP authorization contract tests only."""

    def __init__(self, tokens: Mapping[str, AccessToken]) -> None:
        self._tokens = dict(tokens)

    async def verify_token(self, token: str) -> AccessToken | None:
        return self._tokens.get(token)


class OfflineJwtVerifier:
    """Verify signed JWT claims offline with an explicitly supplied test key.

    Production is expected to use API Gateway's JWT authorizer. This verifier
    proves issuer, audience, expiry, access-token type and scope semantics
    without network calls or an authorization server.
    """

    def __init__(
        self,
        *,
        key: str | bytes,
        algorithms: Sequence[str],
        issuer: str,
        audience: str,
    ) -> None:
        if not algorithms:
            raise ValueError("At least one JWT algorithm must be configured.")
        self._key = key
        self._algorithms = tuple(algorithms)
        self._issuer = issuer
        self._audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["aud", "exp", "iss", "sub"]},
            )
            if claims.get("token_use") != "access":
                return None
            client_id = claims.get("client_id") or claims.get("azp")
            subject = claims.get("sub")
            expires_at = claims.get("exp")
            if not isinstance(client_id, str) or not isinstance(subject, str):
                return None
            if not isinstance(expires_at, int | float):
                return None
            scopes = _extract_scopes(claims)
        except (InvalidTokenError, TypeError, ValueError):
            return None

        minimized_claims: dict[str, Any] = {
            "iss": claims["iss"],
            "sub": subject,
            "aud": claims["aud"],
            "token_use": "access",
        }
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(expires_at),
            resource=self._audience,
            subject=subject,
            claims=minimized_claims,
        )


def _extract_scopes(claims: Mapping[str, Any]) -> list[str]:
    scope = claims.get("scope")
    if isinstance(scope, str):
        return sorted(set(scope.split()))
    scp = claims.get("scp")
    if isinstance(scp, list) and all(isinstance(item, str) for item in scp):
        return sorted(set(scp))
    return []


def caller_from_access_token(token: AccessToken) -> CallerContext:
    claims = token.claims or {}
    issuer = claims.get("iss")
    subject = token.subject or claims.get("sub")
    if not isinstance(issuer, str) or not isinstance(subject, str):
        raise CallerNormalizationError("Validated token lacks issuer or subject.")
    return CallerContext(issuer, subject, frozenset(token.scopes))


def current_authenticated_caller() -> CallerContext:
    token = get_access_token()
    if token is None:
        raise CallerNormalizationError("No validated access-token context exists.")
    return caller_from_access_token(token)


class ScopeChallengeMiddleware:
    """Add the MCP-recommended authoritative scope to 401/403 challenges."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        required_scopes: tuple[str, ...],
    ) -> None:
        self._app = app
        self._scope_value = " ".join(required_scopes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_scope(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] in (
                401,
                403,
            ):
                headers = MutableHeaders(raw=message["headers"])
                challenge = headers.get("www-authenticate")
                if challenge and "scope=" not in challenge:
                    headers["www-authenticate"] = (
                        f'{challenge}, scope="{self._scope_value}"'
                    )
            await send(message)

        await self._app(scope, receive, send_with_scope)


def valid_test_access_token(
    *,
    token: str,
    issuer: str,
    audience: str,
    subject: str = "test-subject",
    client_id: str = "test-client",
    scopes: tuple[str, ...] | None = None,
    expires_at: int | None = None,
) -> AccessToken:
    """Build deterministic validated token metadata without decoding a JWT."""

    return AccessToken(
        token=token,
        client_id=client_id,
        scopes=list(scopes if scopes is not None else (mcp_use_scope(audience),)),
        expires_at=expires_at or int(time()) + 300,
        resource=audience,
        subject=subject,
        claims={
            "iss": issuer,
            "sub": subject,
            "aud": audience,
            "token_use": "access",
        },
    )
