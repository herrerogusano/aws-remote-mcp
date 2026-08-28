"""Local-only MCP Streamable HTTP adapter."""

from __future__ import annotations

from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.core.models import CallerContext, ToolIssue, ToolResult
from aws_remote_mcp.core.operations import build_default_registry
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


def build_tool_service() -> ToolService:
    aws = FakeAwsAdapter(
        responses={
            "synthetic.aws.list_resources": {
                "environment": "local",
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


def create_server() -> MCPServer:
    """Create a fresh server and isolate mutable fake/confirmation state."""

    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Safe local precursor to an authenticated AWS remote MCP server.",
        instructions="All integrations are synthetic or preview-only in this phase.",
    )
    tools = build_tool_service()

    @server.tool(name="diagnostico", structured_output=True)
    def diagnostic() -> dict[str, Any]:
        """Return a non-sensitive local readiness result without network calls."""

        return {
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "transport": "streamable-http",
            "environment": "local",
            "external_side_effects": False,
        }

    @server.tool(name="listar_recursos_aws_sintetico", structured_output=True)
    def list_synthetic_aws_resources() -> dict[str, Any]:
        """Return a bounded synthetic inventory; this never contacts AWS."""

        result = tools.run_aws_operation("synthetic.aws.list_resources", {})
        return serialize_tool_result(result)

    @server.tool(name="preparar_mensaje_telegram", structured_output=True)
    def prepare_telegram_message(message: str) -> dict[str, Any]:
        """Preview a local Telegram message with scoped confirmation metadata."""

        result = tools.prepare_telegram_message(LOCAL_CALLER, "local-preview", message)
        return serialize_tool_result(result)

    @server.tool(name="preparar_tarjeta_trello", structured_output=True)
    def prepare_trello_card(title: str, description: str = "") -> dict[str, Any]:
        """Preview a local-only Trello card and return scoped confirmation metadata."""

        result = tools.prepare_trello_card(
            LOCAL_CALLER,
            "local-preview",
            "local-preview",
            title,
            description,
        )
        return serialize_tool_result(result)

    return server


def transport_security(
    *, allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS
) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(allowed_hosts),
        allowed_origins=list(LOCAL_ALLOWED_ORIGINS),
    )


def create_app(*, allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS) -> Starlette:
    """Build the stateless, JSON-response ASGI application."""

    return create_server().streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_HTTP_REQUEST_BYTES,
        transport_security=transport_security(allowed_hosts=allowed_hosts),
        host=LOCAL_HOST,
    )


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
