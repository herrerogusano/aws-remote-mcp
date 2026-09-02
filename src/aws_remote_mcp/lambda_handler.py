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


def _validated_gateway_event(
    event: dict[str, Any], authorization: AuthorizationConfig
) -> dict[str, Any]:
    """Trust only API Gateway-validated access-token claims and drop the bearer."""

    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise RuntimeError("API Gateway request context is missing.")
    if request_context.get("routeKey") == "POST /mcp":
        authorizer = request_context.get("authorizer")
        jwt_context = authorizer.get("jwt") if isinstance(authorizer, dict) else None
        claims = jwt_context.get("claims") if isinstance(jwt_context, dict) else None
        if not isinstance(claims, dict):
            raise RuntimeError("Validated JWT claims are missing.")
        scopes = claims.get("scope", "")
        required_scope = authorization.required_scopes[0]
        if (
            claims.get("iss") != authorization.issuer_url
            or claims.get("aud") != authorization.resource_server_url
            or claims.get("token_use") != "access"
            or not isinstance(claims.get("sub"), str)
            or not claims["sub"]
            or not isinstance(scopes, str)
            or required_scope not in scopes.split()
        ):
            raise RuntimeError("Validated JWT claims violate the MCP contract.")

    headers = event.get("headers")
    if not isinstance(headers, dict):
        raise RuntimeError("API Gateway headers are missing.")
    sanitized_headers = {
        key: value for key, value in headers.items() if key.lower() != "authorization"
    }
    return {**event, "headers": sanitized_headers}


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
    event = _validated_gateway_event(event, authorization)
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
