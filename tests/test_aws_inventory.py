"""Offline tests for the bounded, allowlisted AWS inventory adapter."""

from __future__ import annotations

from typing import Any, cast

import pytest

from aws_remote_mcp.adapters.aws_inventory import (
    INVENTORY_OPERATION,
    AwsInventoryAdapter,
)
from aws_remote_mcp.adapters.protocols import AdapterError


class FakeLambdaClient:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def list_functions(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return {
            "Functions": [
                {
                    "FunctionName": "safe-function",
                    "FunctionArn": "arn:must-not-leak",
                    "Runtime": "python3.13",
                    "Architectures": ["x86_64"],
                    "Environment": {"Variables": {"SECRET": "must-not-leak"}},
                }
            ],
            "NextMarker": "not-returned-to-caller",
        }


class FakeApiGatewayClient:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[dict[str, Any]] = []

    def get_apis(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return {
            "Items": [
                {
                    "Name": "safe-http-api",
                    "ApiId": "must-not-leak",
                    "ApiEndpoint": "https://must-not-leak.example",
                    "ProtocolType": "HTTP",
                    "DisableExecuteApiEndpoint": True,
                }
            ],
            "NextToken": "not-returned-to-caller",
        }


def build_adapter(
    *,
    lambda_client: FakeLambdaClient | None = None,
    api_client: FakeApiGatewayClient | None = None,
) -> tuple[AwsInventoryAdapter, FakeLambdaClient, FakeApiGatewayClient]:
    lambda_client = lambda_client or FakeLambdaClient()
    api_client = api_client or FakeApiGatewayClient()
    clients = {"lambda": lambda_client, "apigatewayv2": api_client}

    def client_factory(service: str, region: str) -> Any:
        assert region == "eu-west-1"
        return clients[service]

    return (
        AwsInventoryAdapter(region="eu-west-1", client_factory=client_factory),
        lambda_client,
        api_client,
    )


def test_inventory_is_two_non_paginated_requests_with_sanitized_output() -> None:
    adapter, lambda_client, api_client = build_adapter()

    result = adapter.execute(INVENTORY_OPERATION, {})

    assert result.status == "ok"
    assert result.sdk_requests == 2
    assert result.resources == 2
    assert lambda_client.calls == [{"MaxItems": 10}]
    assert api_client.calls == [{"MaxResults": "10"}]
    assert result.data["read_only"] is True
    assert result.data["max_resources_per_service"] == 10
    assert "must-not-leak" not in str(result.data)
    services = result.data["services"]
    assert isinstance(services, dict)
    lambda_service = cast("dict[str, Any]", services["lambda"])
    api_service = cast("dict[str, Any]", services["api_gateway_v2"])
    assert lambda_service["truncated"] is True
    assert api_service["truncated"] is True


def test_one_service_failure_returns_partial_without_raw_exception() -> None:
    raw = RuntimeError("credential and account detail must-not-leak")
    adapter, _, _ = build_adapter(lambda_client=FakeLambdaClient(failure=raw))

    result = adapter.execute(INVENTORY_OPERATION, {})

    assert result.status == "partial"
    assert result.sdk_requests == 2
    assert result.resources == 1
    assert result.issues[0].code == "lambda_inventory_unavailable"
    assert "must-not-leak" not in str(result)


def test_both_service_failures_return_sanitized_error() -> None:
    adapter, _, _ = build_adapter(
        lambda_client=FakeLambdaClient(failure=RuntimeError("lambda raw")),
        api_client=FakeApiGatewayClient(failure=RuntimeError("api raw")),
    )

    result = adapter.execute(INVENTORY_OPERATION, {})

    assert result.status == "error"
    assert result.sdk_requests == 2
    assert result.resources == 0
    assert len(result.issues) == 2


def test_unknown_operation_and_arguments_fail_before_client_creation() -> None:
    adapter, lambda_client, api_client = build_adapter()

    with pytest.raises(AdapterError, match="not supported"):
        adapter.execute("aws.unknown", {})
    with pytest.raises(AdapterError, match="does not accept arguments"):
        adapter.execute(INVENTORY_OPERATION, {"limit": 999})

    assert lambda_client.calls == []
    assert api_client.calls == []


@pytest.mark.parametrize("region", ["us-east-1", "", "EU-WEST-1"])
def test_inventory_refuses_any_other_region(region: str) -> None:
    with pytest.raises(ValueError, match="eu-west-1"):
        AwsInventoryAdapter(region=region)


@pytest.mark.parametrize("limit", [0, 11, 100])
def test_inventory_limit_cannot_exceed_ten(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        AwsInventoryAdapter(region="eu-west-1", max_resources_per_service=limit)
