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
reduces that risk, but repeated warm invocations still require verification.

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

## Result

Mangum 0.22.0 correctly translates the HTTP API v2 event and response contract.
An explicit contract test validates:

1. modern `server/discover`, `tools/list` and `tools/call` events;
2. Host/Origin forwarding behind the API Gateway hostname;
3. repeated warm invocations and ASGI lifespan behavior;
4. JSON response headers and base64 flags;
5. package size and cold-start timing.

The SDK session manager cannot start a second time when one process-global ASGI
app is started and stopped for consecutive Lambda events. Disabling lifespan is
also invalid because its task group is then uninitialized. The selected stateless
adapter therefore constructs a fresh ASGI app and Mangum adapter per invocation,
keeps `lifespan="auto"`. The deployed HTTP API now uses `$default`, so `/mcp`
reaches the ASGI route without a stage prefix.
Two consecutive synthetic events both succeed and expose only the diagnostic and
synthetic AWS tools. This keeps the official SDK lifecycle intact at the cost of
small per-request initialization overhead, which will be measured in DEV.

The Lambda artifact is built for Linux x86_64 using SAM's `python-uv` builder.
It is approximately 30.5 MB uncompressed and contains no Windows-only runtime
packages. No AWS resource was created by this spike.

## Sources

- https://modelcontextprotocol.io/specification/2026-07-28/
- https://py.sdk.modelcontextprotocol.io/
- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html
- https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/building-python-uv.html
- https://github.com/Kludex/mangum
- https://github.com/aws/aws-lambda-web-adapter
