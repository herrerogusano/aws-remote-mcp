"""API Gateway HTTP API v2 entry point for an isolated environment."""

from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Any

from mangum import Mangum

from aws_remote_mcp.adapters.aws_cost_explorer import AwsCostExplorerAdapter
from aws_remote_mcp.adapters.aws_inventory import AwsInventoryAdapter
from aws_remote_mcp.adapters.external_integrations import (
    SsmIntegrationConfigProvider,
    SsmTelegramAdapter,
    SsmTrelloAdapter,
)
from aws_remote_mcp.adapters.protocols import TelegramAdapter, TrelloAdapter
from aws_remote_mcp.core.confirmation import (
    ConfirmationProvider,
    DynamoDbConfirmationGuard,
)
from aws_remote_mcp.core.cost_quota import DynamoDbCostRequestLimiter
from aws_remote_mcp.core.models import CallerContext
from aws_remote_mcp.http_server import create_gateway_app
from aws_remote_mcp.security.authorization import AuthorizationConfig

TELEGRAM_DESTINATIONS = frozenset({"owner"})
TRELLO_DESTINATIONS = frozenset({("portfolio", "inbox")})
AUDIT_LOGGER = logging.getLogger("aws_remote_mcp.audit")
AUDIT_LOGGER.setLevel(logging.INFO)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def _boto_client(service: str, region: str) -> Any:
    boto3 = importlib.import_module("boto3")
    config_module = importlib.import_module("botocore.config")
    config = config_module.Config(
        connect_timeout=2,
        read_timeout=3,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    return boto3.client(service, region_name=region, config=config)


def _external_components(
    region: str,
    environment: str,
    confirmations: ConfirmationProvider | None = None,
) -> tuple[ConfirmationProvider, TelegramAdapter, TrelloAdapter]:
    if confirmations is None:
        table_name = _required_environment("CONFIRMATION_TABLE_NAME")
        confirmations = DynamoDbConfirmationGuard(
            table_name=table_name,
            client=_boto_client("dynamodb", region),
        )
    parameter_name = _required_environment("INTEGRATION_CONFIG_PARAMETER")
    config = SsmIntegrationConfigProvider(
        parameter_name=parameter_name,
        environment=environment,
        region=region,
        client_factory=_boto_client,
    )
    return (
        confirmations,
        SsmTelegramAdapter(config=config),
        SsmTrelloAdapter(config=config),
    )


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
        _gateway_caller(event, authorization)

    headers = event.get("headers")
    if not isinstance(headers, dict):
        raise RuntimeError("API Gateway headers are missing.")
    sanitized_headers = {
        key: value for key, value in headers.items() if key.lower() != "authorization"
    }
    return {**event, "headers": sanitized_headers}


def _gateway_caller(
    event: dict[str, Any], authorization: AuthorizationConfig
) -> CallerContext:
    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise RuntimeError("API Gateway request context is missing.")
    authorizer = request_context.get("authorizer")
    jwt_context = authorizer.get("jwt") if isinstance(authorizer, dict) else None
    claims = jwt_context.get("claims") if isinstance(jwt_context, dict) else None
    if not isinstance(claims, dict):
        raise RuntimeError("Validated JWT claims are missing.")
    scopes = claims.get("scope", "")
    subject = claims.get("sub")
    required_scopes = authorization.required_scopes or ()
    token_use = claims.get("token_use")
    if (
        claims.get("iss") != authorization.issuer_url
        or claims.get("aud") != authorization.resource_server_url
        or (token_use is not None and token_use != "access")
        or not isinstance(subject, str)
        or not subject
        or not isinstance(scopes, str)
        or any(required not in scopes.split() for required in required_scopes)
    ):
        raise RuntimeError("Validated JWT claims violate the MCP contract.")
    return CallerContext(
        issuer=authorization.issuer_url,
        subject=subject,
        scopes=frozenset(scopes.split()),
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Create one stateless ASGI app per event and preserve SDK lifespan rules."""

    environment = _required_environment("APP_ENVIRONMENT")
    if environment not in {"dev", "prod"}:
        raise RuntimeError(
            "APP_ENVIRONMENT must identify the isolated dev or prod deployment."
        )
    allowed_host = _api_gateway_host(event)
    authorization = AuthorizationConfig(
        issuer_url=_required_environment("OAUTH_ISSUER"),
        resource_server_url=_required_environment("MCP_RESOURCE_URL"),
        authorization_server_url=_required_environment("OAUTH_AUTHORIZATION_SERVER"),
        required_scopes=tuple(
            scope for scope in os.environ.get("MCP_REQUIRED_SCOPE", "").split() if scope
        ),
    )
    request_context = event.get("requestContext")
    route_key = (
        request_context.get("routeKey") if isinstance(request_context, dict) else None
    )
    caller = (
        _gateway_caller(event, authorization)
        if route_key == "POST /mcp"
        else CallerContext(authorization.issuer_url, "metadata-route")
    )
    event = _validated_gateway_event(event, authorization)
    external_setting = os.environ.get("EXTERNAL_INTEGRATIONS_ENABLED", "false")
    if external_setting not in {"true", "false"}:
        raise RuntimeError("EXTERNAL_INTEGRATIONS_ENABLED must be true or false.")
    external_enabled = external_setting == "true"
    cost_setting = os.environ.get("COST_EXPLORER_ENABLED", "false")
    if cost_setting not in {"true", "false"}:
        raise RuntimeError("COST_EXPLORER_ENABLED must be true or false.")
    cost_enabled = cost_setting == "true"
    confirmations: ConfirmationProvider | None = None
    cost_request_limiter = None
    telegram: TelegramAdapter | None = None
    trello: TrelloAdapter | None = None
    if cost_enabled:
        table_name = _required_environment("CONFIRMATION_TABLE_NAME")
        ddb_client = _boto_client("dynamodb", _required_environment("AWS_REGION"))
        confirmations = DynamoDbConfirmationGuard(
            table_name=table_name,
            client=ddb_client,
        )
        cost_request_limiter = DynamoDbCostRequestLimiter(
            table_name=table_name,
            client=ddb_client,
        )
    if external_enabled:
        region = _required_environment("AWS_REGION")
        if confirmations is None:
            confirmations, telegram, trello = _external_components(region, environment)
        else:
            confirmations, telegram, trello = _external_components(
                region, environment, confirmations
            )
    cost_explorer = None
    if cost_enabled:
        cost_explorer = AwsCostExplorerAdapter(
            billing_view_arn=_required_environment("COST_EXPLORER_BILLING_VIEW_ARN")
        )
    app = create_gateway_app(
        authorization=authorization,
        allowed_hosts=(allowed_host,),
        environment=environment,
        aws_adapter=AwsInventoryAdapter(
            region=_required_environment("AWS_REGION"),
            resource_explorer_view_arn=(
                os.environ.get("RESOURCE_EXPLORER_VIEW_ARN", "").strip() or None
            ),
        ),
        caller_provider=lambda: caller,
        include_external_writes=external_enabled,
        include_cost_explorer=cost_enabled,
        aws_cost_explorer_adapter=cost_explorer,
        cost_request_limiter=cost_request_limiter,
        confirmations=confirmations,
        telegram_adapter=telegram,
        trello_adapter=trello,
        telegram_destinations=TELEGRAM_DESTINATIONS,
        trello_destinations=TRELLO_DESTINATIONS,
        audit_sink=lambda record: AUDIT_LOGGER.info(
            json.dumps(record, separators=(",", ":"), sort_keys=True)
        ),
        audit_request_id=str(getattr(context, "aws_request_id", "unknown")),
    )
    adapter = Mangum(
        app,
        lifespan="auto",
    )
    return adapter(event, context)
