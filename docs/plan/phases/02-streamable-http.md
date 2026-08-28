# Phase 2 — Local Streamable HTTP MCP

## Goal
Turn the core into a real local remote-style MCP server using the official MCP Python SDK.

## Protocol
Before coding, verify the current official MCP spec and SDK. Use **Streamable HTTP**, not legacy HTTP+SSE.

Evaluate current SDK support for stateless HTTP, JSON responses, one `/mcp` endpoint and current protocol-version behavior. Choose the mode best suited to Lambda/API Gateway and document why.

## Work
1. Add official MCP Python SDK.
2. Implement thin MCP adapter.
3. Expose safe diagnostic tool, synthetic AWS tool and Telegram/Trello preview tools.
4. Bind locally to localhost only.
5. Configure host/Origin validation and request-body limits.
6. Test current protocol lifecycle/discovery, tools/list, tools/call, malformed JSON-RPC, unknown tools, oversized payloads and invalid Origin.
7. Test with MCP Inspector or official SDK client.
8. No real AWS/Telegram/Trello.
9. Add local run docs.

## Lambda compatibility spike
Compare realistic ways to adapt the SDK HTTP/ASGI app to Lambda, e.g. a Python ASGI adapter, Lambda Web Adapter or small native bridge. Evaluate correctness, lifecycle, package size and serverless suitability rather than guessing.

Record the preferred approach for Phase 4.

## Done
A local MCP client connects via Streamable HTTP and calls safe tools.
