"""Bounded AWS control-plane inventory adapter with a fixed operation allowlist."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any, Literal

from aws_remote_mcp.adapters.protocols import (
    AdapterError,
    AdapterIssue,
    AwsAdapterResult,
)
from aws_remote_mcp.core.models import JsonValue

INVENTORY_OPERATION = "aws.inventory.list"
MAX_RESOURCES_PER_SERVICE = 10
SUPPORTED_REGION = "eu-west-1"
MAX_NAME_CHARS = 128

type AwsClientFactory = Callable[[str, str], Any]


def _safe_string(value: object, *, fallback: str = "unknown") -> str:
    if not isinstance(value, str) or not value:
        return fallback
    return value[:MAX_NAME_CHARS]


def _boto_client(service: str, region: str) -> Any:
    """Create a runtime SDK client only when the real inventory tool is called."""

    boto3 = importlib.import_module("boto3")
    config_module = importlib.import_module("botocore.config")
    config = config_module.Config(
        connect_timeout=2,
        read_timeout=3,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    return boto3.client(service, region_name=region, config=config)


class AwsInventoryAdapter:
    """Execute exactly two non-paginated, read-only AWS inventory requests."""

    def __init__(
        self,
        *,
        region: str,
        client_factory: AwsClientFactory = _boto_client,
        max_resources_per_service: int = MAX_RESOURCES_PER_SERVICE,
    ) -> None:
        if region != SUPPORTED_REGION:
            raise ValueError(f"AWS inventory is restricted to {SUPPORTED_REGION}.")
        if not 1 <= max_resources_per_service <= MAX_RESOURCES_PER_SERVICE:
            raise ValueError(
                f"Inventory limit must be between 1 and {MAX_RESOURCES_PER_SERVICE}."
            )
        self._region = region
        self._client_factory = client_factory
        self._limit = max_resources_per_service

    def execute(
        self, operation: str, arguments: Mapping[str, JsonValue]
    ) -> AwsAdapterResult:
        if operation != INVENTORY_OPERATION:
            raise AdapterError(
                "aws_operation_not_supported",
                "The AWS adapter operation is not supported.",
            )
        if arguments:
            raise AdapterError(
                "invalid_inventory_arguments",
                "AWS inventory does not accept arguments.",
            )

        services: dict[str, JsonValue] = {}
        issues: list[AdapterIssue] = []
        resources = 0
        sdk_requests = 0
        successful_services = 0

        sdk_requests += 1
        try:
            lambda_resources, lambda_truncated = self._list_lambda_functions()
            services["lambda"] = {
                "status": "ok",
                "truncated": lambda_truncated,
                "resources": lambda_resources,
            }
            resources += len(lambda_resources)
            successful_services += 1
        except Exception:
            services["lambda"] = {
                "status": "unavailable",
                "truncated": False,
                "resources": [],
            }
            issues.append(
                AdapterIssue(
                    "lambda_inventory_unavailable",
                    "Lambda inventory could not be read.",
                )
            )

        sdk_requests += 1
        try:
            api_resources, api_truncated = self._list_http_apis()
            services["api_gateway_v2"] = {
                "status": "ok",
                "truncated": api_truncated,
                "resources": api_resources,
            }
            resources += len(api_resources)
            successful_services += 1
        except Exception:
            services["api_gateway_v2"] = {
                "status": "unavailable",
                "truncated": False,
                "resources": [],
            }
            issues.append(
                AdapterIssue(
                    "api_gateway_inventory_unavailable",
                    "API Gateway inventory could not be read.",
                )
            )

        status: Literal["ok", "partial", "error"] = (
            "ok"
            if successful_services == 2
            else "partial"
            if successful_services == 1
            else "error"
        )
        return AwsAdapterResult(
            data={
                "region": self._region,
                "read_only": True,
                "max_resources_per_service": self._limit,
                "services": services,
            },
            sdk_requests=sdk_requests,
            resources=resources,
            status=status,
            issues=tuple(issues),
        )

    def _list_lambda_functions(self) -> tuple[list[JsonValue], bool]:
        client = self._client_factory("lambda", self._region)
        response = client.list_functions(MaxItems=self._limit)
        functions = response.get("Functions", [])
        if not isinstance(functions, list):
            raise TypeError("Invalid Lambda inventory response.")
        resources: list[JsonValue] = []
        for item in functions[: self._limit]:
            if not isinstance(item, dict):
                continue
            architectures = item.get("Architectures", [])
            architecture = (
                architectures[0]
                if isinstance(architectures, list) and architectures
                else "unknown"
            )
            resources.append(
                {
                    "service": "lambda",
                    "resource_type": "AWS::Lambda::Function",
                    "name": _safe_string(item.get("FunctionName")),
                    "runtime": _safe_string(item.get("Runtime")),
                    "architecture": _safe_string(architecture),
                }
            )
        return resources, bool(response.get("NextMarker"))

    def _list_http_apis(self) -> tuple[list[JsonValue], bool]:
        client = self._client_factory("apigatewayv2", self._region)
        response = client.get_apis(MaxResults=str(self._limit))
        apis = response.get("Items", [])
        if not isinstance(apis, list):
            raise TypeError("Invalid API Gateway inventory response.")
        resources: list[JsonValue] = []
        for item in apis[: self._limit]:
            if not isinstance(item, dict):
                continue
            resources.append(
                {
                    "service": "api_gateway_v2",
                    "resource_type": "AWS::ApiGatewayV2::Api",
                    "name": _safe_string(item.get("Name")),
                    "protocol": _safe_string(item.get("ProtocolType")),
                    "default_endpoint_disabled": bool(
                        item.get("DisableExecuteApiEndpoint", False)
                    ),
                }
            )
        return resources, bool(response.get("NextToken"))
