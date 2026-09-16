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
from aws_remote_mcp.adapters.protocols import (
    AwsAdapter,
    AwsAdapterResult,
    CostExplorerAdapter,
    TelegramAdapter,
    TrelloAdapter,
)
from aws_remote_mcp.core.audit import build_tool_audit_record
from aws_remote_mcp.core.confirmation import ConfirmationGuard, ConfirmationProvider
from aws_remote_mcp.core.cost_quota import (
    CostRequestLimiter,
    InMemoryCostRequestLimiter,
)
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
type AuditSink = Callable[[dict[str, Any]], None]


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


def build_tool_service(
    *,
    environment: str = "local",
    aws_adapter: AwsAdapter | None = None,
    aws_cost_explorer_adapter: CostExplorerAdapter | None = None,
    cost_request_limiter: CostRequestLimiter | None = None,
    confirmations: ConfirmationProvider | None = None,
    telegram_adapter: TelegramAdapter | None = None,
    trello_adapter: TrelloAdapter | None = None,
    telegram_destinations: frozenset[str] = frozenset({"local-preview"}),
    trello_destinations: frozenset[tuple[str, str]] = frozenset(
        {("local-preview", "local-preview")}
    ),
) -> ToolService:
    aws = aws_adapter or FakeAwsAdapter(
        responses={
            "aws.inventory.list": AwsAdapterResult(
                data={
                    "region": "eu-west-1",
                    "read_only": True,
                    "max_resources_per_service": 10,
                    "fixture": True,
                    "services": {
                        "lambda": {
                            "status": "ok",
                            "truncated": False,
                            "resources": [
                                {
                                    "service": "lambda",
                                    "resource_type": "AWS::Lambda::Function",
                                    "name": "example-only",
                                    "runtime": "python3.13",
                                    "architecture": "x86_64",
                                }
                            ],
                        },
                        "api_gateway_v2": {
                            "status": "ok",
                            "truncated": False,
                            "resources": [],
                        },
                    },
                },
                sdk_requests=0,
                resources=1,
            )
        }
    )
    local_limiter = (
        InMemoryCostRequestLimiter()
        if environment == "local"
        and aws_cost_explorer_adapter is not None
        and cost_request_limiter is None
        else cost_request_limiter
    )
    return ToolService(
        operations=build_default_registry(),
        confirmations=confirmations or ConfirmationGuard(),
        aws=aws,
        aws_cost_explorer=aws_cost_explorer_adapter,
        cost_request_limiter=local_limiter,
        telegram=telegram_adapter or FakeTelegramAdapter(),
        trello=trello_adapter or FakeTrelloAdapter(),
        telegram_destinations=telegram_destinations,
        trello_destinations=trello_destinations,
    )


def create_server(
    *,
    caller_provider: Callable[[], CallerContext] = lambda: LOCAL_CALLER,
    auth_settings: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
    environment: str = "local",
    include_previews: bool = True,
    include_external_writes: bool = False,
    include_cost_explorer: bool = False,
    aws_adapter: AwsAdapter | None = None,
    aws_cost_explorer_adapter: CostExplorerAdapter | None = None,
    cost_request_limiter: CostRequestLimiter | None = None,
    confirmations: ConfirmationProvider | None = None,
    telegram_adapter: TelegramAdapter | None = None,
    trello_adapter: TrelloAdapter | None = None,
    telegram_destinations: frozenset[str] = frozenset({"local-preview"}),
    trello_destinations: frozenset[tuple[str, str]] = frozenset(
        {("local-preview", "local-preview")}
    ),
    audit_sink: AuditSink | None = None,
    audit_request_id: str = "local-request",
) -> MCPServer:
    """Create a fresh server and isolate mutable fake/confirmation state."""

    server = MCPServer(
        SERVER_NAME,
        version=SERVER_VERSION,
        description="Authenticated, cost-aware AWS remote MCP server.",
        instructions=(
            "AWS inventory and Resource Explorer search are read-only and "
            "bounded; Cost Explorer queries require explicit single-use "
            "confirmation, one USD 0.01 request, and a global three-request "
            "UTC-month limit; external writes require an exact, expiring, "
            "single-use confirmation."
        ),
        auth=auth_settings,
        token_verifier=token_verifier,
    )
    tools = build_tool_service(
        environment=environment,
        aws_adapter=aws_adapter,
        aws_cost_explorer_adapter=aws_cost_explorer_adapter,
        cost_request_limiter=cost_request_limiter,
        confirmations=confirmations,
        telegram_adapter=telegram_adapter,
        trello_adapter=trello_adapter,
        telegram_destinations=telegram_destinations,
        trello_destinations=trello_destinations,
    )

    def audited_result(
        tool_name: str,
        result: ToolResult,
        caller: CallerContext | None = None,
    ) -> dict[str, Any]:
        if audit_sink is not None:
            try:
                record = build_tool_audit_record(
                    tool=tool_name,
                    result=result,
                    caller=caller or caller_provider(),
                    environment=environment,
                    request_id=audit_request_id,
                )
                audit_sink(dict(record))
            except Exception:
                # Audit failure must not turn a completed provider write into an
                # ambiguous tool response that invites a duplicate retry.
                pass
        return serialize_tool_result(result)

    @server.tool(name="diagnostico", structured_output=True)
    def diagnostic() -> dict[str, Any]:
        """Return a non-sensitive local readiness result without network calls."""

        if audit_sink is not None:
            audited_result("diagnostico", ToolResult(status="ok"))
        return {
            "status": "ok",
            "server": SERVER_NAME,
            "version": SERVER_VERSION,
            "transport": "streamable-http",
            "environment": environment,
            "external_side_effects": False,
        }

    @server.tool(name="listar_inventario_aws", structured_output=True)
    def list_aws_inventory() -> dict[str, Any]:
        """Return bounded read-only Lambda and API Gateway inventory."""

        result = tools.run_aws_operation("aws.inventory.list", {})
        return audited_result("listar_inventario_aws", result)

    @server.tool(name="buscar_recursos_aws", structured_output=True)
    def search_aws_resources(query: str = "*", limit: int = 25) -> dict[str, Any]:
        """Search an explicitly configured AWS Resource Explorer view safely."""

        result = tools.run_aws_operation(
            "aws.resource_explorer.search", {"query": query, "limit": limit}
        )
        return audited_result("buscar_recursos_aws", result)

    if include_cost_explorer:

        @server.tool(name="preparar_consulta_costes_aws", structured_output=True)
        def prepare_aws_cost_query(
            start_date: str,
            end_date: str,
            granularity: str,
            group_by: str,
        ) -> dict[str, Any]:
            """Preview one bounded Cost Explorer request and issue confirmation."""

            caller = caller_provider()
            result = tools.prepare_aws_cost_query(
                caller, start_date, end_date, granularity, group_by
            )
            return audited_result("preparar_consulta_costes_aws", result, caller)

        @server.tool(name="consultar_costes_aws", structured_output=True)
        def execute_aws_cost_query(
            confirmation: str,
            start_date: str,
            end_date: str,
            granularity: str,
            group_by: str,
        ) -> dict[str, Any]:
            """Consume confirmation before one Cost Explorer API request."""

            caller = caller_provider()
            result = tools.execute_aws_cost_query(
                caller,
                confirmation,
                start_date,
                end_date,
                granularity,
                group_by,
            )
            return audited_result("consultar_costes_aws", result, caller)

    if include_previews and include_external_writes:

        @server.tool(name="preparar_mensaje_telegram", structured_output=True)
        def prepare_remote_telegram_message(
            destination: str, message: str
        ) -> dict[str, Any]:
            """Preview one allowlisted Telegram message and issue confirmation."""

            caller = caller_provider()
            result = tools.prepare_telegram_message(caller, destination, message)
            return audited_result("preparar_mensaje_telegram", result, caller)

        @server.tool(name="enviar_mensaje_telegram", structured_output=True)
        def execute_remote_telegram_message(
            confirmation: str, destination: str, message: str
        ) -> dict[str, Any]:
            """Consume confirmation before one Telegram write attempt."""

            caller = caller_provider()
            result = tools.execute_telegram_message(
                caller, confirmation, destination, message
            )
            return audited_result("enviar_mensaje_telegram", result, caller)

        @server.tool(name="preparar_tarjeta_trello", structured_output=True)
        def prepare_remote_trello_card(
            board: str, list_name: str, title: str, description: str = ""
        ) -> dict[str, Any]:
            """Preview one allowlisted Trello card and issue confirmation."""

            caller = caller_provider()
            result = tools.prepare_trello_card(
                caller, board, list_name, title, description
            )
            return audited_result("preparar_tarjeta_trello", result, caller)

        @server.tool(name="crear_tarjeta_trello", structured_output=True)
        def execute_remote_trello_card(
            confirmation: str,
            board: str,
            list_name: str,
            title: str,
            description: str = "",
        ) -> dict[str, Any]:
            """Consume confirmation before one Trello write attempt."""

            caller = caller_provider()
            result = tools.execute_trello_card(
                caller,
                confirmation,
                board,
                list_name,
                title,
                description,
            )
            return audited_result("crear_tarjeta_trello", result, caller)

    elif include_previews:

        @server.tool(name="preparar_mensaje_telegram", structured_output=True)
        def prepare_telegram_message(message: str) -> dict[str, Any]:
            """Preview a local Telegram message with confirmation metadata."""

            caller = caller_provider()
            result = tools.prepare_telegram_message(caller, "local-preview", message)
            return audited_result("preparar_mensaje_telegram", result, caller)

        @server.tool(name="preparar_tarjeta_trello", structured_output=True)
        def prepare_trello_card(title: str, description: str = "") -> dict[str, Any]:
            """Preview a local Trello card with confirmation metadata."""

            caller = caller_provider()
            result = tools.prepare_trello_card(
                caller,
                "local-preview",
                "local-preview",
                title,
                description,
            )
            return audited_result("preparar_tarjeta_trello", result, caller)

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
    caller_provider: Callable[[], CallerContext] = lambda: LOCAL_CALLER,
    allowed_hosts: tuple[str, ...] = LOCAL_ALLOWED_HOSTS,
    allowed_origins: tuple[str, ...] = LOCAL_ALLOWED_ORIGINS,
    environment: str = "local",
    include_previews: bool = True,
    include_external_writes: bool = False,
    include_cost_explorer: bool = False,
    aws_adapter: AwsAdapter | None = None,
    aws_cost_explorer_adapter: CostExplorerAdapter | None = None,
    cost_request_limiter: CostRequestLimiter | None = None,
    confirmations: ConfirmationProvider | None = None,
    telegram_adapter: TelegramAdapter | None = None,
    trello_adapter: TrelloAdapter | None = None,
    telegram_destinations: frozenset[str] = frozenset({"local-preview"}),
    trello_destinations: frozenset[tuple[str, str]] = frozenset(
        {("local-preview", "local-preview")}
    ),
    audit_sink: AuditSink | None = None,
    audit_request_id: str = "local-request",
) -> Starlette:
    """Build the stateless, JSON-response ASGI application."""

    return create_server(
        caller_provider=caller_provider,
        environment=environment,
        include_previews=include_previews,
        include_external_writes=include_external_writes,
        include_cost_explorer=include_cost_explorer,
        aws_adapter=aws_adapter,
        aws_cost_explorer_adapter=aws_cost_explorer_adapter,
        cost_request_limiter=cost_request_limiter,
        confirmations=confirmations,
        telegram_adapter=telegram_adapter,
        trello_adapter=trello_adapter,
        telegram_destinations=telegram_destinations,
        trello_destinations=trello_destinations,
        audit_sink=audit_sink,
        audit_request_id=audit_request_id,
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
        required_scopes=authorization.required_scopes or (),
    )
    return app


def create_gateway_app(
    *,
    authorization: AuthorizationConfig,
    allowed_hosts: tuple[str, ...],
    environment: str,
    aws_adapter: AwsAdapter,
    aws_cost_explorer_adapter: CostExplorerAdapter | None = None,
    cost_request_limiter: CostRequestLimiter | None = None,
    caller_provider: Callable[[], CallerContext] = lambda: LOCAL_CALLER,
    include_external_writes: bool = False,
    include_cost_explorer: bool = False,
    confirmations: ConfirmationProvider | None = None,
    telegram_adapter: TelegramAdapter | None = None,
    trello_adapter: TrelloAdapter | None = None,
    telegram_destinations: frozenset[str] = frozenset(),
    trello_destinations: frozenset[tuple[str, str]] = frozenset(),
    audit_sink: AuditSink | None = None,
    audit_request_id: str = "gateway-request",
) -> Starlette:
    """Build the API Gateway app with public RFC 9728 metadata.

    API Gateway validates bearer tokens before invoking the MCP route. The
    metadata route remains public so compatible clients can discover OAuth.
    """

    app = create_app(
        allowed_hosts=allowed_hosts,
        allowed_origins=(),
        environment=environment,
        caller_provider=caller_provider,
        include_previews=include_external_writes,
        include_external_writes=include_external_writes,
        include_cost_explorer=include_cost_explorer,
        aws_adapter=aws_adapter,
        aws_cost_explorer_adapter=aws_cost_explorer_adapter,
        cost_request_limiter=cost_request_limiter,
        confirmations=confirmations,
        telegram_adapter=telegram_adapter,
        trello_adapter=trello_adapter,
        telegram_destinations=telegram_destinations,
        trello_destinations=trello_destinations,
        audit_sink=audit_sink,
        audit_request_id=audit_request_id,
    )
    app.routes.extend(
        create_protected_resource_routes(
            resource_url=AnyHttpUrl(authorization.resource_server_url),
            authorization_servers=[
                AnyHttpUrl(str(authorization.authorization_server_url))
            ],
            scopes_supported=list(authorization.required_scopes or ()),
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
