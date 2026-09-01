"""API Gateway HTTP API v2 entry point for the safe DEV skeleton."""

from __future__ import annotations

import os
from typing import Any

from mangum import Mangum

from aws_remote_mcp.http_server import create_gateway_app
from aws_remote_mcp.security.authorization import AuthorizationConfig


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def _api_gateway_host(event: dict[str, Any]) -> str:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise RuntimeError("API Gateway request context is missing.")
    domain_name = request_context.get("domainName")
    if not isinstance(domain_name, str) or not domain_name:
        raise RuntimeError("API Gateway domain name is missing.")
    region = _required_environment("AWS_REGION")
    expected_suffix = f".execute-api.{region}.amazonaws.com"
    if not domain_name.endswith(expected_suffix):
        raise RuntimeError("Unexpected API Gateway domain name.")
    return domain_name


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create one stateless ASGI app per event and preserve SDK lifespan rules."""

    environment = _required_environment("APP_ENVIRONMENT")
    if environment != "dev":
        raise RuntimeError(
            "This Lambda deployment is restricted to APP_ENVIRONMENT=dev."
        )
    allowed_host = _api_gateway_host(event)
    authorization = AuthorizationConfig(
        issuer_url=_required_environment("COGNITO_ISSUER"),
        resource_server_url=_required_environment("MCP_RESOURCE_URL"),
    )
    app = create_gateway_app(
        authorization=authorization,
        allowed_hosts=(allowed_host,),
        environment=environment,
    )
    adapter = Mangum(
        app,
        lifespan="auto",
    )
    return adapter(event, context)
