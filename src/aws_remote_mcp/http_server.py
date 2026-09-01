"""Local-only MCP Streamable HTTP adapter."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.core.models import CallerContext, ToolIssue, ToolResult
from aws_remote_mcp.core.operations import build_default_registry
from aws_remote_mcp.security.authorization import (
    AuthorizationConfig,
    ScopeChallengeMiddleware,
    current_authenticated_caller,
)
from aws_remote_mcp.services.tools import ToolService

SERVER_NAME = "aws-remote-mcp"
SERVER_VERSION = "0.1.0"
MCP_PATH = "/mcp"
LOCAL_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MAX_HTTP_REQUEST_BYTES = 64 * 1024
LOCAL_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
LOCAL_ALLOWED_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
)
LOCAL_CALLER = CallerContext("local://aws-remote-mcp", "local-development")


def _serialize_issue(issue: ToolIssue) -> dict[str, Any]:
    return {
        "code": issue.code,
        "message": issue.message,
        "retryable": issue.retryable,
    }


def serialize_tool_result(result: ToolResult) -> dict[str, Any]:
    serialized: dict[str, Any] = {
        "status": result.status,
        "data": result.data,
        "warnings": [_serialize_issue(issue) for issue in result.warnings],
        "errors": [_serialize_issue(issue) for issue in result.errors],
        "counters": {
            "sdk_requests": result.counters.sdk_requests,
            "resources": result.counters.resources,
            "external_writes_attempted": result.counters.external_writes_attempted,
            "external_writes_succeeded": result.counters.external_writes_succeeded,
        },
    }
    if result.confirmation is not None:
        serialized["confirmation"] = {
            "token": result.confirmation.token,
            "action": result.confirmation.action,
            "payload_digest": result.confirmation.payload_digest,
            "expires_at": result.confirmation.expires_at,
        }
    return serialized


def build_tool_service(*, environment: str = "local") -> ToolService:
    aws = FakeAwsAdapter(
        responses={
            "synthetic.aws.list_resources": {
                "environment": environment,
                "synthetic": True,
                "resources": [
                    {
                        "service": "lambda",
                        "resource_type": "AWS::Lambda::Function",
                        "name": "example-only",
                        "region": "eu-west-1",
                    }
                ],
            }
        }
    )
    return ToolService(
        operations=build_default_registry(),
        confirmations=ConfirmationGuard(),
        aws=aws,
        telegram=FakeTelegramAdapter(),
        trello=FakeTrelloAdapter(),
        telegram_destinations=frozenset({"local-preview"}),
        trello_destinations=frozenset({("local-preview", "local-preview")}),
    )


def create_server(
    *,
    caller_provider: Callable[[], CallerContext] = lambda: LOCAL_CALLER,
    auth_settings: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    environment: str = "local",
    include_previews: bool = True,
) -> MCPServer:
    """Create a fresh server and isolate mutable fake/confirmation state."""

    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Safe local precursor to an authenticated AWS remote MCP server.",
        instructions="All current integrations are synthetic or preview-only.",
        auth=auth_settings,
        token_verifier=token_verifier,
    )
    tools = build_tool_service(environment=environment)

    @server.tool(name="diagnostico", structured_output=True)
    def diagnostic() -> dict[str, Any]:
        """Return a non-sensitive local readiness result without network calls."""

        return {
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "transport": "streamable-http",
            "environment": environment,
            "external_side_effects": False,
        }

    @server.tool(name="listar_recursos_aws_sintetico", structured_output=True)
    def list_synthetic_aws_resources() -> dict[str, Any]:
        """Return a bounded synthetic inventory; this never contacts AWS."""

        result = tools.run_aws_operation("synthetic.aws.list_resources", {})
        return serialize_tool_result(result)

    if include_previews:

        @server.tool(name="preparar_mensaje_telegram", structured_output=True)
        def prepare_telegram_message(message: str) -> dict[str, Any]:
            """Preview a local Telegram message with confirmation metadata."""

            result = tools.prepare_telegram_message(
                caller_provider(), "local-preview", message
            )
            return serialize_tool_result(result)

        @server.tool(name="preparar_tarjeta_trello", structured_output=True)
        def prepare_trello_card(title: str, description: str = "") -> dict[str, Any]:
            """Preview a local Trello card with confirmation metadata."""

            result = tools.prepare_trello_card(
                caller_provider(),
                "local-preview",
                "local-preview",
                title,
                description,
            )
            return serialize_tool_result(result)

    return server


def transport_security(
    *,
    allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS,
    allowed_origins: tuple[str, ...] = LOCAL_ALLOWED_ORIGINS,
) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(allowed_hosts),
        allowed_origins=list(allowed_origins),
    )


def create_app(
    *,
    allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS,
    allowed_origins: tuple[str, ...] = LOCAL_ALLOWED_ORIGINS,
    environment: str = "local",
    include_previews: bool = True,
) -> Starlette:
    """Build the stateless, JSON-response ASGI application."""

    return create_server(
        environment=environment, include_previews=include_previews
    ).streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_HTTP_REQUEST_BYTES,
        transport_security=transport_security(
            allowed_hosts=allowed_hosts, allowed_origins=allowed_origins
        ),
        host=LOCAL_HOST,
    )


def create_protected_app(
    *,
    authorization: AuthorizationConfig,
    token_verifier: TokenVerifier,
    allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS,
) -> Starlette:
    """Build the same MCP app as an OAuth-protected resource server."""

    app = create_server(
        caller_provider=current_authenticated_caller,
        auth_settings=authorization.sdk_settings(),
        token_verifier=token_verifier,
    ).streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_HTTP_REQUEST_BYTES,
        transport_security=transport_security(allowed_hosts=allowed_hosts),
        host=LOCAL_HOST,
    )
    app.add_middleware(
        ScopeChallengeMiddleware,
        required_scopes=authorization.required_scopes,
    )
    return app


def create_gateway_app(
    *,
    authorization: AuthorizationConfig,
    allowed_hosts: tuple[str, ...],
    environment: str,
) -> Starlette:
    """Build the API Gateway app with public RFC 9728 metadata.

    API Gateway validates bearer tokens before invoking the MCP route. The
    metadata route remains public so compatible clients can discover Cognito.
    """

    app = create_app(
        allowed_hosts=allowed_hosts,
        allowed_origins=(),
        environment=environment,
        include_previews=False,
    )
    app.routes.extend(
        create_protected_resource_routes(
            resource_url=AnyHttpUrl(authorization.resource_server_url),
            authorization_servers=[AnyHttpUrl(authorization.issuer_url)],
            scopes_supported=list(authorization.required_scopes),
            resource_name="AWS Remote MCP",
        )
    )
    return app


def main() -> None:
    """Run a local server bound only to loopback."""

    create_server().run(
        transport="streamable-http",
        host=LOCAL_HOST,
        port=DEFAULT_PORT,
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_HTTP_REQUEST_BYTES,
        transport_security=transport_security(),
    )


if __name__ == "__main__":
    main()
