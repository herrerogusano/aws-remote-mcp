"""Current-protocol MCP Streamable HTTP contract tests."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any, cast

import pytest
import uvicorn
from mcp import Client
from mcp_types.jsonrpc import HEADER_MISMATCH
from starlette.testclient import TestClient

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.adapters.protocols import AwsAdapterResult
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.http_server import (
    LOCAL_CALLER,
    MAX_HTTP_REQUEST_BYTES,
    create_app,
)


class FakeCostExplorerAdapter:
    billing_view_arn = "arn:aws:billing::123456789012:billingview/primary"

    def __init__(self) -> None:
        self.calls: list[Any] = []

    def get_cost_and_usage(self, query: Any) -> AwsAdapterResult:
        self.calls.append(query)
        return AwsAdapterResult(
            data={"region": "us-east-1", "read_only": True},
            sdk_requests=1,
            resources=0,
        )


PROTOCOL_VERSION = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "contract-test", "version": "1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


@pytest.fixture
def http_client() -> Iterator[TestClient]:
    app = create_app(allowed_hosts=("testserver",))
    with TestClient(app) as client:
        yield client


def modern_request(
    method: str,
    *,
    params: dict[str, Any] | None = None,
    name: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    request_params = dict(params or {})
    request_params["_meta"] = META
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "mcp-protocol-version": PROTOCOL_VERSION,
        "mcp-method": method,
    }
    if name is not None:
        headers["mcp-name"] = name
    return (
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": request_params},
        headers,
    )


def response_json(response: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", response.json())


def test_modern_discovery_and_tool_listing(http_client: TestClient) -> None:
    body, headers = modern_request("server/discover")
    discovery = http_client.post("/mcp", json=body, headers=headers)
    assert discovery.status_code == 200
    assert PROTOCOL_VERSION in response_json(discovery)["result"]["supportedVersions"]

    body, headers = modern_request("tools/list")
    listing = http_client.post("/mcp", json=body, headers=headers)
    tool_names = {tool["name"] for tool in response_json(listing)["result"]["tools"]}

    assert listing.status_code == 200
    assert tool_names == {
        "diagnostico",
        "listar_inventario_aws",
        "listar_recursos_proyecto_aws",
        "buscar_recursos_aws",
        "preparar_mensaje_telegram",
        "preparar_tarjeta_trello",
    }


def test_resource_explorer_search_is_registered_read_only_and_audited_safely() -> None:
    query = "service:lambda region:eu-west-1"
    secret = "arn:aws:lambda:eu-west-1:123456789012:function:private-resource"
    aws = FakeAwsAdapter(
        responses={
            "aws.resource_explorer.search": AwsAdapterResult(
                data={
                    "query": query,
                    "read_only": True,
                    "resources": [{"resource_id": "function:private-resource"}],
                },
                sdk_requests=1,
                resources=1,
            )
        }
    )
    telegram = FakeTelegramAdapter()
    trello = FakeTrelloAdapter()
    records: list[dict[str, Any]] = []
    app = create_app(
        allowed_hosts=("testserver",),
        aws_adapter=aws,
        telegram_adapter=telegram,
        trello_adapter=trello,
        audit_sink=records.append,
        audit_request_id="resource-search-1",
    )

    with TestClient(app) as client:
        body, headers = modern_request("tools/list")
        listing = client.post("/mcp", json=body, headers=headers)
        names = {tool["name"] for tool in response_json(listing)["result"]["tools"]}
        body, headers = modern_request(
            "tools/call",
            params={
                "name": "buscar_recursos_aws",
                "arguments": {"query": query, "limit": 2},
            },
            name="buscar_recursos_aws",
        )
        response = client.post("/mcp", json=body, headers=headers)
        content = response_json(response)["result"]["structuredContent"]

    assert "buscar_recursos_aws" in names
    assert response.status_code == 200
    assert content["status"] == "ok"
    assert content["data"]["read_only"] is True
    assert content["counters"]["external_writes_attempted"] == 0
    assert aws.calls == [("aws.resource_explorer.search", {"query": query, "limit": 2})]
    assert telegram.calls == []
    assert trello.calls == []
    assert len(records) == 1
    assert records[0]["tool"] == "buscar_recursos_aws"
    assert records[0]["counters"]["sdk_requests"] == 1
    assert records[0]["counters"]["resources"] == 1
    assert records[0]["counters"]["external_writes_attempted"] == 0
    assert query not in str(records)
    assert secret not in str(records)


def test_resource_explorer_mcp_tool_supplies_bounded_defaults() -> None:
    aws = FakeAwsAdapter(
        responses={
            "aws.resource_explorer.search": AwsAdapterResult(
                data={"region": "eu-west-1", "query": "*", "max_results": 25},
                sdk_requests=1,
                resources=0,
            )
        }
    )
    app = create_app(allowed_hosts=("testserver",), aws_adapter=aws)

    with TestClient(app) as client:
        body, headers = modern_request(
            "tools/call",
            params={"name": "buscar_recursos_aws", "arguments": {}},
            name="buscar_recursos_aws",
        )
        response = client.post("/mcp", json=body, headers=headers)

    content = response_json(response)["result"]["structuredContent"]
    assert response.status_code == 200
    assert content["status"] == "ok"
    assert aws.calls == [("aws.resource_explorer.search", {"query": "*", "limit": 25})]


def test_project_inventory_mcp_tool_calls_allowlisted_read() -> None:
    aws = FakeAwsAdapter(
        responses={
            "aws.cloudformation.project_inventory": AwsAdapterResult(
                data={
                    "resources": [
                        {
                            "stack": "aws-remote-mcp-dev",
                            "logical_id": "Function",
                            "resource_type": "AWS::Lambda::Function",
                            "physical_id": "dev-function",
                            "status": "CREATE_COMPLETE",
                        }
                    ],
                    "total": 1,
                    "complete": True,
                    "sdk_requests": 8,
                    "writes": 0,
                },
                sdk_requests=8,
                resources=1,
            )
        }
    )
    app = create_app(allowed_hosts=("testserver",), aws_adapter=aws)

    with TestClient(app) as client:
        body, headers = modern_request(
            "tools/call",
            params={
                "name": "listar_recursos_proyecto_aws",
                "arguments": {},
            },
            name="listar_recursos_proyecto_aws",
        )
        response = client.post("/mcp", json=body, headers=headers)

    content = response_json(response)["result"]["structuredContent"]
    assert response.status_code == 200
    assert content["status"] == "ok"
    assert content["data"]["complete"] is True
    assert content["data"]["writes"] == 0
    assert content["counters"]["sdk_requests"] == 8
    assert aws.calls == [("aws.cloudformation.project_inventory", {})]


def test_tool_call_returns_structured_content(http_client: TestClient) -> None:
    body, headers = modern_request(
        "tools/call",
        params={"name": "diagnostico", "arguments": {}},
        name="diagnostico",
    )

    response = http_client.post("/mcp", json=body, headers=headers)
    result = response_json(response)["result"]

    assert response.status_code == 200
    assert result["isError"] is False
    assert result["structuredContent"]["transport"] == "streamable-http"
    assert result["structuredContent"]["external_side_effects"] is False


def test_tool_call_emits_allowlisted_audit_record() -> None:
    records: list[dict[str, object]] = []
    app = create_app(
        allowed_hosts=("testserver",),
        audit_sink=records.append,
        audit_request_id="request-123",
    )

    with TestClient(app) as client:
        body, headers = modern_request(
            "tools/call",
            params={"name": "diagnostico", "arguments": {}},
            name="diagnostico",
        )
        response = client.post("/mcp", json=body, headers=headers)

    assert response.status_code == 200
    assert records == [
        {
            "schema_version": 1,
            "event_type": "mcp_tool_result",
            "environment": "local",
            "request_id": "request-123",
            "caller_fingerprint": LOCAL_CALLER.fingerprint,
            "tool": "diagnostico",
            "status": "ok",
            "warning_codes": [],
            "error_codes": [],
            "counters": {
                "sdk_requests": 0,
                "resources": 0,
                "external_writes_attempted": 0,
                "external_writes_succeeded": 0,
            },
        }
    ]


def test_audit_sink_failure_does_not_change_tool_response() -> None:
    def failing_sink(_record: dict[str, Any]) -> None:
        raise RuntimeError("audit unavailable")

    app = create_app(
        allowed_hosts=("testserver",),
        audit_sink=failing_sink,
        audit_request_id="request-123",
    )

    with TestClient(app) as client:
        body, headers = modern_request(
            "tools/call",
            params={"name": "diagnostico", "arguments": {}},
            name="diagnostico",
        )
        response = client.post("/mcp", json=body, headers=headers)

    assert response.status_code == 200
    assert response_json(response)["result"]["structuredContent"]["status"] == "ok"


def test_external_tools_require_prepare_then_exact_confirmation() -> None:
    telegram = FakeTelegramAdapter()
    app = create_app(
        allowed_hosts=("testserver",),
        include_external_writes=True,
        confirmations=ConfirmationGuard(),
        telegram_adapter=telegram,
        trello_adapter=FakeTrelloAdapter(),
        telegram_destinations=frozenset({"owner"}),
        trello_destinations=frozenset({("portfolio", "inbox")}),
    )
    with TestClient(app) as client:
        body, headers = modern_request("tools/list")
        listing = client.post("/mcp", json=body, headers=headers)
        names = {tool["name"] for tool in response_json(listing)["result"]["tools"]}
        assert names == {
            "diagnostico",
            "listar_inventario_aws",
            "listar_recursos_proyecto_aws",
            "buscar_recursos_aws",
            "preparar_mensaje_telegram",
            "enviar_mensaje_telegram",
            "preparar_tarjeta_trello",
            "crear_tarjeta_trello",
        }

        body, headers = modern_request(
            "tools/call",
            params={
                "name": "preparar_mensaje_telegram",
                "arguments": {"destination": "owner", "message": "hello"},
            },
            name="preparar_mensaje_telegram",
        )
        prepared = client.post("/mcp", json=body, headers=headers)
        prepared_content = response_json(prepared)["result"]["structuredContent"]
        token = prepared_content["confirmation"]["token"]
        assert prepared_content["status"] == "confirmation_required"
        assert telegram.calls == []

        body, headers = modern_request(
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
        executed = client.post("/mcp", json=body, headers=headers)
        content = response_json(executed)["result"]["structuredContent"]

    assert content["status"] == "ok"
    assert content["counters"]["external_writes_attempted"] == 1
    assert telegram.calls == [("owner", "hello")]


def test_cost_explorer_tools_are_opt_in_and_require_confirmation() -> None:
    ce = FakeCostExplorerAdapter()
    app = create_app(
        allowed_hosts=("testserver",),
        include_cost_explorer=True,
        aws_cost_explorer_adapter=ce,
        confirmations=ConfirmationGuard(),
    )
    args = {
        "start_date": "2026-01-01",
        "end_date": "2026-01-02",
        "granularity": "DAILY",
        "group_by": "SERVICE",
    }

    with TestClient(app) as client:
        body, headers = modern_request("tools/list")
        listing = client.post("/mcp", json=body, headers=headers)
        names = {tool["name"] for tool in response_json(listing)["result"]["tools"]}
        assert "preparar_consulta_costes_aws" in names
        assert "consultar_costes_aws" in names

        body, headers = modern_request(
            "tools/call",
            params={
                "name": "preparar_consulta_costes_aws",
                "arguments": args,
            },
            name="preparar_consulta_costes_aws",
        )
        prepared = client.post("/mcp", json=body, headers=headers)
        preview = response_json(prepared)["result"]["structuredContent"]
        assert preview["status"] == "confirmation_required"
        assert preview["data"]["preview"]["max_cost_usd"] == "0.01"
        assert ce.calls == []
        token = preview["confirmation"]["token"]

        body, headers = modern_request(
            "tools/call",
            params={
                "name": "consultar_costes_aws",
                "arguments": {**args, "confirmation": token},
            },
            name="consultar_costes_aws",
        )
        executed = client.post("/mcp", json=body, headers=headers)
        content = response_json(executed)["result"]["structuredContent"]

    assert content["status"] == "ok"
    assert content["counters"]["sdk_requests"] == 1
    assert content["counters"]["external_writes_attempted"] == 0
    assert len(ce.calls) == 1


def test_unknown_tool_is_a_protocol_error_result(http_client: TestClient) -> None:
    body, headers = modern_request(
        "tools/call",
        params={"name": "does_not_exist", "arguments": {}},
        name="does_not_exist",
    )

    response = http_client.post("/mcp", json=body, headers=headers)
    result = response_json(response)["result"]

    assert response.status_code == 200
    assert result["isError"] is True


def test_malformed_json_rpc_is_rejected(http_client: TestClient) -> None:
    _, headers = modern_request("tools/list")

    response = http_client.post("/mcp", content=b"{not-json", headers=headers)

    assert response.status_code == 400


def test_oversized_request_is_rejected_before_protocol_handling(
    http_client: TestClient,
) -> None:
    _, headers = modern_request("tools/list")

    response = http_client.post(
        "/mcp", content=b"x" * (MAX_HTTP_REQUEST_BYTES + 1), headers=headers
    )

    assert response.status_code == 413


def test_invalid_origin_and_host_are_rejected(http_client: TestClient) -> None:
    body, headers = modern_request("tools/list")
    invalid_origin = http_client.post(
        "/mcp", json=body, headers={**headers, "origin": "https://evil.example"}
    )
    invalid_host = http_client.post(
        "/mcp", json=body, headers={**headers, "host": "evil.example"}
    )

    assert invalid_origin.status_code == 403
    assert invalid_host.status_code == 421


def test_protocol_header_body_mismatch_is_rejected(http_client: TestClient) -> None:
    body, headers = modern_request("tools/list")
    headers["mcp-method"] = "tools/call"

    response = http_client.post("/mcp", json=body, headers=headers)
    error = response_json(response)["error"]

    assert response.status_code == 400
    assert error["code"] == HEADER_MISMATCH


def unused_local_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


@pytest.fixture
def live_mcp_url() -> Iterator[str]:
    port = unused_local_port()
    config = uvicorn.Config(
        create_app(), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=2)
        pytest.fail("Local MCP test server did not start.")
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_official_sdk_client_uses_modern_streamable_http(live_mcp_url: str) -> None:
    async def scenario() -> None:
        async with Client(live_mcp_url, mode=PROTOCOL_VERSION) as client:
            listing = await client.list_tools()
            assert "diagnostico" in {tool.name for tool in listing.tools}

            called = await client.call_tool("diagnostico", {})
            assert called.is_error is False
            assert called.structured_content is not None
            assert called.structured_content["environment"] == "local"

    asyncio.run(scenario())
