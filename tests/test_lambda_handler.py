"""API Gateway HTTP API v2 to MCP/Lambda contract tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

import pytest

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.adapters.protocols import AwsAdapterResult
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.lambda_handler import (
    _gateway_caller,
    _validated_gateway_event,
    handler,
)
from aws_remote_mcp.security.authorization import AuthorizationConfig

API_HOST = "example.execute-api.eu-west-1.amazonaws.com"
PROTOCOL_VERSION = "2026-07-28"
ISSUER = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_example"
AUTHORIZATION_SERVER = "https://login.example.auth.eu-west-1.amazoncognito.com"
RESOURCE = f"https://{API_HOST}/mcp"
REQUIRED_SCOPE = f"{RESOURCE}/use"


@pytest.fixture(autouse=True)
def gateway_authorization_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SERVER", AUTHORIZATION_SERVER)
    monkeypatch.setenv("MCP_RESOURCE_URL", RESOURCE)
    monkeypatch.setenv("MCP_REQUIRED_SCOPE", REQUIRED_SCOPE)


@dataclass(slots=True)
class FakeLambdaContext:
    aws_request_id: str = "lambda-request-1"
    function_name: str = "aws-remote-mcp-dev"
    function_version: str = "$LATEST"
    invoked_function_arn: str = "arn:aws:lambda:eu-west-1:000000000000:function:test"
    memory_limit_in_mb: int = 256
    log_group_name: str = "/aws/lambda/aws-remote-mcp-dev"
    log_stream_name: str = "test"

    @staticmethod
    def get_remaining_time_in_millis() -> int:
        return 15_000


def http_api_event(
    method: str,
    *,
    params: dict[str, Any] | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    request_params = dict(params or {})
    request_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientInfo": {
            "name": "lambda-contract-test",
            "version": "1",
        },
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "host": API_HOST,
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": request_params,
    }
    return {
        "version": "2.0",
        "routeKey": "POST /mcp",
        "rawPath": "/mcp",
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "accountId": "000000000000",
            "apiId": "example",
            "domainName": API_HOST,
            "domainPrefix": "example",
            "http": {
                "method": "POST",
                "path": "/mcp",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "contract-test",
            },
            "requestId": "api-request-1",
            "routeKey": "POST /mcp",
            "authorizer": {
                "jwt": {
                    "claims": {
                        "iss": ISSUER,
                        "aud": RESOURCE,
                        "sub": "test-subject",
                        "scope": REQUIRED_SCOPE,
                        "token_use": "access",
                    },
                    "scopes": [REQUIRED_SCOPE],
                }
            },
            "stage": "$default",
            "time": "",
            "timeEpoch": 0,
        },
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }


def response_body(response: dict[str, Any]) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(response["body"]))


def test_repeated_events_use_fresh_sdk_lifespan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event("tools/list")
    context = FakeLambdaContext()

    first = handler(event, context)
    second = handler(event, context)

    for response in (first, second):
        assert response["statusCode"] == 200
        names = {tool["name"] for tool in response_body(response)["result"]["tools"]}
        assert names == {
            "diagnostico",
            "listar_inventario_aws",
            "buscar_recursos_aws",
        }


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_diagnostic_identifies_isolated_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", environment)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event(
        "tools/call",
        params={"name": "diagnostico", "arguments": {}},
        name="diagnostico",
    )

    response = handler(event, FakeLambdaContext())
    content = response_body(response)["result"]["structuredContent"]

    assert response["statusCode"] == 200
    assert content["environment"] == environment
    assert content["external_side_effects"] is False


def test_lambda_emits_sanitized_tool_audit_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    messages: list[str] = []
    monkeypatch.setattr(
        "aws_remote_mcp.lambda_handler.AUDIT_LOGGER.info", messages.append
    )
    event = http_api_event(
        "tools/call",
        params={"name": "diagnostico", "arguments": {}},
        name="diagnostico",
    )

    response = handler(event, FakeLambdaContext())
    record = json.loads(messages[0])

    assert response["statusCode"] == 200
    assert record["event_type"] == "mcp_tool_result"
    assert record["request_id"] == "lambda-request-1"
    assert record["tool"] == "diagnostico"
    assert record["caller_fingerprint"]
    assert "arguments" not in record
    assert "confirmation" not in record


def test_lambda_inventory_uses_injected_bounded_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("RESOURCE_EXPLORER_VIEW_ARN", "")
    fake = FakeAwsAdapter(
        responses={
            "aws.inventory.list": AwsAdapterResult(
                data={"region": "eu-west-1", "services": {}},
                sdk_requests=2,
                resources=3,
            )
        }
    )

    def inventory_adapter(
        *, region: str, resource_explorer_view_arn: str | None = None
    ) -> FakeAwsAdapter:
        assert region == "eu-west-1"
        assert resource_explorer_view_arn is None
        return fake

    monkeypatch.setattr(
        "aws_remote_mcp.lambda_handler.AwsInventoryAdapter", inventory_adapter
    )
    event = http_api_event(
        "tools/call",
        params={"name": "listar_inventario_aws", "arguments": {}},
        name="listar_inventario_aws",
    )

    response = handler(event, FakeLambdaContext())
    content = response_body(response)["result"]["structuredContent"]

    assert response["statusCode"] == 200
    assert content["status"] == "ok"
    assert content["counters"]["sdk_requests"] == 2
    assert content["counters"]["resources"] == 3
    assert fake.calls == [("aws.inventory.list", {})]


@pytest.mark.parametrize("environment", ["", "staging"])
def test_lambda_environment_fails_safe(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", environment)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    with pytest.raises(RuntimeError):
        handler(http_api_event("tools/list"), FakeLambdaContext())


def test_lambda_requires_api_gateway_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event("tools/list")
    request_context = cast("dict[str, Any]", event["requestContext"])
    request_context["domainName"] = "attacker.example"

    with pytest.raises(RuntimeError, match="domain name"):
        handler(event, FakeLambdaContext())


def test_gateway_serves_public_protected_resource_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event("metadata")
    event["routeKey"] = "GET /.well-known/oauth-protected-resource/mcp"
    event["rawPath"] = "/.well-known/oauth-protected-resource/mcp"
    event["body"] = None
    request_context = cast("dict[str, Any]", event["requestContext"])
    request_context["routeKey"] = event["routeKey"]
    http_context = cast("dict[str, Any]", request_context["http"])
    http_context["method"] = "GET"
    http_context["path"] = event["rawPath"]

    response = handler(event, FakeLambdaContext())
    metadata = response_body(response)

    assert response["statusCode"] == 200
    assert metadata["resource"] == RESOURCE
    assert metadata["authorization_servers"] == [f"{AUTHORIZATION_SERVER}/"]
    assert metadata["scopes_supported"] == [REQUIRED_SCOPE]
    assert metadata["bearer_methods_supported"] == ["header"]


def test_gateway_drops_bearer_before_entering_application() -> None:
    event = http_api_event("tools/list")
    headers = cast("dict[str, str]", event["headers"])
    headers["Authorization"] = "Bearer must-not-reach-the-app"
    authorization = AuthorizationConfig(issuer_url=ISSUER, resource_server_url=RESOURCE)

    sanitized = _validated_gateway_event(event, authorization)

    assert "Authorization" in headers
    assert all(key.lower() != "authorization" for key in sanitized["headers"])


def test_gateway_caller_uses_validated_issuer_subject_and_scopes() -> None:
    event = http_api_event("tools/list")
    authorization = AuthorizationConfig(issuer_url=ISSUER, resource_server_url=RESOURCE)

    caller = _gateway_caller(event, authorization)

    assert caller.issuer == ISSUER
    assert caller.subject == "test-subject"
    assert caller.scopes == frozenset({REQUIRED_SCOPE})


def test_gateway_accepts_audience_bound_provider_token_without_cognito_claims() -> None:
    event = http_api_event("tools/list")
    request_context = cast("dict[str, Any]", event["requestContext"])
    authorizer = cast("dict[str, Any]", request_context["authorizer"])
    jwt_context = cast("dict[str, Any]", authorizer["jwt"])
    claims = cast("dict[str, Any]", jwt_context["claims"])
    claims.pop("token_use")
    claims["scope"] = "openid profile"
    authorization = AuthorizationConfig(
        issuer_url=ISSUER,
        authorization_server_url=AUTHORIZATION_SERVER,
        resource_server_url=RESOURCE,
        required_scopes=(),
    )

    caller = _gateway_caller(event, authorization)

    assert caller.subject == "test-subject"
    assert caller.scopes == frozenset({"openid", "profile"})


def test_lambda_handles_external_oauth_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("OAUTH_ISSUER", "https://portfolio.authkit.app")
    monkeypatch.setenv("OAUTH_AUTHORIZATION_SERVER", "https://portfolio.authkit.app")
    monkeypatch.setenv("MCP_REQUIRED_SCOPE", "openid")
    event = http_api_event("tools/list")
    request_context = cast("dict[str, Any]", event["requestContext"])
    authorizer = cast("dict[str, Any]", request_context["authorizer"])
    jwt_context = cast("dict[str, Any]", authorizer["jwt"])
    claims = cast("dict[str, Any]", jwt_context["claims"])
    claims["iss"] = "https://portfolio.authkit.app"
    claims["scope"] = "openid profile"
    claims.pop("token_use")

    response = handler(event, FakeLambdaContext())

    assert response["statusCode"] == 200


def test_lambda_external_write_uses_confirmation_bound_to_gateway_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.setenv("EXTERNAL_INTEGRATIONS_ENABLED", "true")
    confirmations = ConfirmationGuard()
    telegram = FakeTelegramAdapter()
    trello = FakeTrelloAdapter()
    monkeypatch.setattr(
        "aws_remote_mcp.lambda_handler._external_components",
        lambda _region, _environment: (confirmations, telegram, trello),
    )
    prepare_event = http_api_event(
        "tools/call",
        params={
            "name": "preparar_mensaje_telegram",
            "arguments": {"destination": "owner", "message": "hello"},
        },
        name="preparar_mensaje_telegram",
    )
    prepared = handler(prepare_event, FakeLambdaContext())
    prepared_content = response_body(prepared)["result"]["structuredContent"]
    token = prepared_content["confirmation"]["token"]

    execute_event = http_api_event(
        "tools/call",
        params={
            "name": "enviar_mensaje_telegram",
            "arguments": {
                "confirmation": token,
                "destination": "owner",
                "message": "hello",
            },
        },
        name="enviar_mensaje_telegram",
    )
    executed = handler(execute_event, FakeLambdaContext())
    content = response_body(executed)["result"]["structuredContent"]

    assert content["status"] == "ok"
    assert content["counters"]["external_writes_succeeded"] == 1
    assert telegram.calls == [("owner", "hello")]


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://wrong.example"),
        ("aud", "https://wrong.example/mcp"),
        ("token_use", "id"),
        ("sub", ""),
        ("scope", "openid"),
    ],
)
def test_lambda_rejects_invalid_gateway_jwt_claims(
    monkeypatch: pytest.MonkeyPatch, claim: str, value: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event("tools/list")
    request_context = cast("dict[str, Any]", event["requestContext"])
    authorizer = cast("dict[str, Any]", request_context["authorizer"])
    jwt_context = cast("dict[str, Any]", authorizer["jwt"])
    claims = cast("dict[str, Any]", jwt_context["claims"])
    claims[claim] = value

    with pytest.raises(RuntimeError, match="claims violate"):
        handler(event, FakeLambdaContext())


@pytest.mark.parametrize(
    "name",
    ["OAUTH_ISSUER", "OAUTH_AUTHORIZATION_SERVER", "MCP_RESOURCE_URL"],
)
def test_lambda_requires_gateway_authorization_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError, match=name):
        handler(http_api_event("tools/list"), FakeLambdaContext())
