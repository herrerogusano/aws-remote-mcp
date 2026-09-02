# Bounded AWS inventory

## Contract

`listar_inventario_aws` is a read-only MCP tool backed by one fixed registry
operation: `aws.inventory.list`. Callers cannot supply a service, operation,
region, page token or result limit.

Each execution is restricted to `eu-west-1` and performs:

| Service | SDK operation | Requests | Maximum returned |
| --- | --- | ---: | ---: |
| Lambda | `ListFunctions(MaxItems=10)` | 1 | 10 |
| API Gateway v2 | `GetApis(MaxResults=10)` | 1 | 10 |

Pagination is never followed. The SDK uses two-second connection and
three-second read timeouts with total attempts set to one. The enclosing Lambda
still has its ten-second timeout.

## Data minimization

The tool returns resource names, CloudFormation type, Lambda runtime and
architecture, or API protocol and default-endpoint-disabled state. It never
returns:

- ARNs or account IDs;
- API IDs or endpoint URLs;
- Lambda environment variables or code configuration;
- tags;
- pagination tokens;
- raw SDK exceptions or credentials.

A failed service becomes a generic warning while the other service can return a
partial result. If both fail, the result is a sanitized error. Counters report
exact SDK requests and resources; external-write counters remain zero.

## Deployed IAM

The Lambda execution role gains only:

```text
lambda:ListFunctions
  Resource: *
  Condition: aws:RequestedRegion = eu-west-1

apigateway:GET
  Resource: arn:<partition>:apigateway:eu-west-1::/apis
```

AWS does not support resource-level scoping for `ListFunctions`, so its wildcard
is isolated to that one list action and constrained by region. No managed
`ReadOnlyAccess`, write action or credential-bearing read is added.

## Cost and exposure

The management reads have no separately documented per-call price. A remote
tool call still uses the existing metered API Gateway request and Lambda
execution. Those remain protected by JWT, throttle 1/1, a 15-request tripwire,
the five-minute independent deadline and the default closed state.

The implementation and role change were deployed while the API remained
disabled and Lambda concurrency remained zero on 2026-09-03. The post-deployment
audit found exactly the two inventory statements, no managed policy, three
unchanged routes, no temporary alarm or schedule, and no collector invocation.
Invoking the real collector remains a separate operational gate.

## Evidence checked 2026-09-02

- https://docs.aws.amazon.com/lambda/latest/api/API_ListFunctions.html
- https://docs.aws.amazon.com/apigatewayv2/latest/api-reference/apis.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/api-gateway/pricing/
