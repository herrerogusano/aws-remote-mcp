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

from aws_remote_mcp.http_server import (
    MAX_HTTP_REQUEST_BYTES,
    create_app,
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
        "listar_recursos_aws_sintetico",
        "preparar_mensaje_telegram",
        "preparar_tarjeta_trello",
    }


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
