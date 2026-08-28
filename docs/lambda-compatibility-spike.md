# Lambda compatibility spike

Checked 2026-08-28 against MCP Python SDK 2.1.1 and the current 2026-07-28
protocol revision.

## Protocol/runtime choice

The local server uses the official SDK's ASGI application with:

- Streamable HTTP at one `/mcp` endpoint;
- `stateless_http=True`;
- `json_response=True`;
- 64 KiB request-body limit;
- explicit Host and Origin allowlists;
- loopback-only local binding.

The current protocol is request-stateless and the SDK supports the modern
`server/discover` lifecycle. JSON responses avoid relying on long-lived SSE,
which fits the bounded API Gateway HTTP API and Lambda request/response model.
API Gateway HTTP API currently has a 30-second integration timeout and 10 MB
payload quota; application limits will remain substantially lower.

## Adaptation options

### Mangum

Mangum adapts ASGI directly to API Gateway HTTP API v2/Lambda events and supports
ASGI lifespan. It is a small Python dependency and keeps the official MCP ASGI
application unchanged. The main risk is lifespan startup/shutdown per Lambda
invocation and its interaction with the SDK session manager; stateless mode
reduces that risk but Phase 4 must verify repeated warm invocations.

### AWS Lambda Web Adapter

The AWS Lambda Web Adapter is an extension that translates API Gateway events to
real HTTP requests sent to a locally running web server. It preserves familiar
HTTP server behavior and warm-process lifespan well, but adds an extension/layer,
startup/readiness behavior, an internal listener and more packaging/operations
than this small Python service currently needs.

### Custom native bridge

A custom API Gateway event-to-ASGI or event-to-MCP bridge could minimize package
count, but it would duplicate header, body, lifespan, binary response and error
translation semantics. A bridge built against SDK internals would also be brittle
and risks creating a non-compliant MCP-like endpoint.

## Phase 4 preference

Start with Mangum and an explicit HTTP API v2 event contract test. Validate:

1. modern `server/discover`, `tools/list` and `tools/call` events;
2. Host/Origin forwarding behind the API Gateway hostname;
3. repeated warm invocations and ASGI lifespan behavior;
4. JSON response headers and base64 flags;
5. package size and cold-start timing.

If repeated lifecycle behavior is incorrect, evaluate the AWS Lambda Web Adapter
before any custom bridge. No AWS resource is created by this spike.

## Sources

- https://modelcontextprotocol.io/specification/2026-07-28/
- https://py.sdk.modelcontextprotocol.io/
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html
- https://github.com/Kludex/mangum
- https://github.com/aws/aws-lambda-web-adapter
