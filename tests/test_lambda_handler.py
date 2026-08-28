"""API Gateway HTTP API v2 to MCP/Lambda contract tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

import pytest

from aws_remote_mcp.lambda_handler import handler

API_HOST = "example.execute-api.eu-west-1.amazonaws.com"
PROTOCOL_VERSION = "2026-07-28"


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
        "rawPath": "/dev/mcp",
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "accountId": "000000000000",
            "apiId": "example",
            "domainName": API_HOST,
            "domainPrefix": "example",
            "http": {
                "method": "POST",
                "path": "/dev/mcp",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "contract-test",
            },
            "requestId": "api-request-1",
            "routeKey": "POST /mcp",
            "stage": "dev",
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
        assert names == {"diagnostico", "listar_recursos_aws_sintetico"}


def test_dev_diagnostic_identifies_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "dev")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    event = http_api_event(
        "tools/call",
        params={"name": "diagnostico", "arguments": {}},
        name="diagnostico",
    )

    response = handler(event, FakeLambdaContext())
    content = response_body(response)["result"]["structuredContent"]

    assert response["statusCode"] == 200
    assert content["environment"] == "dev"
    assert content["external_side_effects"] is False


@pytest.mark.parametrize("environment", ["", "prod", "staging"])
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
