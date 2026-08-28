"""Offline OAuth resource-server and JWT verification contract tests."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from typing import Any, cast

import jwt
import pytest
from starlette.testclient import TestClient

from aws_remote_mcp.http_server import create_protected_app
from aws_remote_mcp.security.authorization import (
    MCP_USE_SCOPE,
    AuthorizationConfig,
    OfflineJwtVerifier,
    StaticTokenVerifier,
    caller_from_access_token,
    valid_test_access_token,
)

PROTOCOL_VERSION = "2026-07-28"
ISSUER = "https://auth.example.com"
RESOURCE = "https://mcp.example.com/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
VALID_BEARER = "opaque-valid-test-token"


def modern_request(
    method: str,
    *,
    params: dict[str, Any] | None = None,
    name: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    request_params = dict(params or {})
    request_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientInfo": {
            "name": "auth-contract-test",
            "version": "1",
        },
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    return (
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": request_params},
        headers,
    )


@pytest.fixture
def authorization() -> AuthorizationConfig:
    return AuthorizationConfig(issuer_url=ISSUER, resource_server_url=RESOURCE)


@pytest.fixture
def protected_client(authorization: AuthorizationConfig) -> Iterator[TestClient]:
    access_token = valid_test_access_token(
        token=VALID_BEARER,
        issuer=ISSUER,
        audience=RESOURCE,
    )
    app = create_protected_app(
        authorization=authorization,
        token_verifier=StaticTokenVerifier({VALID_BEARER: access_token}),
        allowed_hosts=("testserver",),
    )
    with TestClient(app) as client:
        yield client


def test_protected_resource_metadata_is_public(
    protected_client: TestClient, authorization: AuthorizationConfig
) -> None:
    response = protected_client.get(METADATA_PATH)
    metadata = cast("dict[str, Any]", response.json())

    assert response.status_code == 200
    assert metadata["resource"] == RESOURCE
    assert metadata["authorization_servers"] == [f"{ISSUER}/"]
    assert metadata["scopes_supported"] == [MCP_USE_SCOPE]
    assert authorization.resource_metadata_url.endswith(METADATA_PATH)


@pytest.mark.parametrize(
    ("authorization_header", "expected_error"),
    [(None, "invalid_token"), ("Bearer unknown-token", "invalid_token")],
)
def test_missing_or_invalid_token_returns_401_challenge(
    protected_client: TestClient,
    authorization: AuthorizationConfig,
    authorization_header: str | None,
    expected_error: str,
) -> None:
    body, headers = modern_request("tools/list")
    if authorization_header is not None:
        headers["authorization"] = authorization_header

    response = protected_client.post("/mcp", json=body, headers=headers)
    challenge = response.headers["www-authenticate"]

    assert response.status_code == 401
    assert f'error="{expected_error}"' in challenge
    assert f'scope="{MCP_USE_SCOPE}"' in challenge
    assert f'resource_metadata="{authorization.resource_metadata_url}"' in challenge


def test_insufficient_scope_returns_403_challenge(
    authorization: AuthorizationConfig,
) -> None:
    token = "valid-without-scope"
    access_token = valid_test_access_token(
        token=token, issuer=ISSUER, audience=RESOURCE, scopes=()
    )
    app = create_protected_app(
        authorization=authorization,
        token_verifier=StaticTokenVerifier({token: access_token}),
        allowed_hosts=("testserver",),
    )
    body, headers = modern_request("tools/list")
    headers["authorization"] = f"Bearer {token}"

    with TestClient(app) as client:
        response = client.post("/mcp", json=body, headers=headers)

    challenge = response.headers["www-authenticate"]
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in challenge
    assert f'scope="{MCP_USE_SCOPE}"' in challenge


def test_valid_token_can_call_tool_without_token_passthrough(
    protected_client: TestClient,
) -> None:
    body, headers = modern_request(
        "tools/call",
        params={
            "name": "preparar_mensaje_telegram",
            "arguments": {"message": "preview only"},
        },
        name="preparar_mensaje_telegram",
    )
    headers["authorization"] = f"Bearer {VALID_BEARER}"

    response = protected_client.post("/mcp", json=body, headers=headers)

    assert response.status_code == 200
    assert VALID_BEARER not in response.text
    assert "confirmation_required" in response.text


def encode_jwt(
    secret: str,
    *,
    issuer: str = ISSUER,
    audience: str = RESOURCE,
    expires_at: int | None = None,
    token_use: str = "access",
    scope: str = MCP_USE_SCOPE,
) -> str:
    return jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": "user-123",
            "client_id": "client-123",
            "exp": expires_at or int(time.time()) + 300,
            "iat": int(time.time()),
            "token_use": token_use,
            "scope": scope,
        },
        secret,
        algorithm="HS256",
    )


@pytest.mark.parametrize(
    "encoded",
    [
        encode_jwt("wrong-signature-key-that-is-at-least-32-bytes"),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            issuer="https://wrong-issuer.example",
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            audience="https://wrong-resource.example/mcp",
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            expires_at=int(time.time()) - 1,
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            token_use="id",
        ),
    ],
)
def test_invalid_jwt_conditions_return_401(
    authorization: AuthorizationConfig, encoded: str
) -> None:
    verifier = OfflineJwtVerifier(
        key="offline-test-key-with-no-production-value",
        algorithms=("HS256",),
        issuer=ISSUER,
        audience=RESOURCE,
    )
    app = create_protected_app(
        authorization=authorization,
        token_verifier=verifier,
        allowed_hosts=("testserver",),
    )
    body, headers = modern_request("tools/list")
    headers["authorization"] = f"Bearer {encoded}"

    with TestClient(app) as client:
        response = client.post("/mcp", json=body, headers=headers)

    assert response.status_code == 401
    assert encoded not in response.text
    assert encoded not in response.headers["www-authenticate"]


def test_offline_jwt_verifier_normalizes_minimal_caller() -> None:
    secret = "offline-test-key-with-no-production-value"
    encoded = encode_jwt(secret, scope=f"openid {MCP_USE_SCOPE}")
    verifier = OfflineJwtVerifier(
        key=secret, algorithms=("HS256",), issuer=ISSUER, audience=RESOURCE
    )

    verified = asyncio.run(verifier.verify_token(encoded))

    assert verified is not None
    caller = caller_from_access_token(verified)
    assert caller.subject == "user-123"
    assert caller.issuer == ISSUER
    assert caller.scopes == frozenset({"openid", MCP_USE_SCOPE})
    assert encoded not in repr(caller)
    assert verified.claims == {
        "iss": ISSUER,
        "sub": "user-123",
        "aud": RESOURCE,
        "token_use": "access",
    }


@pytest.mark.parametrize(
    "encoded",
    [
        encode_jwt("wrong-signature-key-that-is-at-least-32-bytes"),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            issuer="https://wrong-issuer.example",
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            audience="https://wrong-resource.example/mcp",
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            expires_at=int(time.time()) - 1,
        ),
        encode_jwt(
            "offline-test-key-with-no-production-value",
            token_use="id",
        ),
    ],
)
def test_offline_jwt_verifier_rejects_invalid_tokens(encoded: str) -> None:
    verifier = OfflineJwtVerifier(
        key="offline-test-key-with-no-production-value",
        algorithms=("HS256",),
        issuer=ISSUER,
        audience=RESOURCE,
    )

    assert asyncio.run(verifier.verify_token(encoded)) is None
