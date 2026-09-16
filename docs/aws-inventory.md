# Bounded AWS inventory and Resource Explorer search

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

The Lambda execution role gains these two base statements:

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

## Optional Resource Explorer search

Resource Explorer is a separate read-only MCP capability, not an extension of
`listar_inventario_aws`. It performs one `resource-explorer-2:Search` request
per tool call, returns at most 50 matches, and does not follow pagination. The
query uses a single configured view in `eu-west-1`; callers cannot choose a
view ARN or AWS region.

This capability is disabled by default. To opt in, a deployment must provide
`ResourceExplorerViewArn` as the exact ARN of a view that already exists in
`eu-west-1`. The same value is supplied to Lambda as
`RESOURCE_EXPLORER_VIEW_ARN`. An empty value leaves the environment variable
empty and omits the Resource Explorer IAM statement, so search is unavailable.
The template does not create or configure Resource Explorer, an index, a view,
a service-linked role, or any other service resource. An operator must arrange
the existing view and any required indexing separately before opting in; this
project's deployment and validation procedures do not perform setup calls.
The view and indexes remain externally managed and are not changed or deleted
when this application's stack is rolled back or removed.

When enabled, IAM grants only `resource-explorer-2:Search` on that exact view
ARN, with `aws:RequestedRegion=eu-west-1` and
`resource-explorer-2:Operation=Search`. The operation condition is important
because AWS maps the distinct `ListResources` API operation to the same IAM
action; this role is limited to the `Search` API operation. It grants no
`GetView`, index or view listing, setup, creation, mutation, or
service-linked-role permission. The existing view's filters remain in force. A
view in `eu-west-1` searches across Regions only if it is in the Region with an
already-configured aggregator index; otherwise results are limited to the
view's Region.

AWS documentation is inconsistent about whether `GetView` is also needed:
the Search API reference and Service Authorization Reference list `Search` as
the operation's minimum permission, while the troubleshooting guide says to
grant `GetView` and `Search`. This implementation follows the operation-specific
API reference and passes the view ARN directly. Closed DEV validation on
2026-09-16 successfully called the configured view with this policy, proving
that `Search` alone is sufficient for this runtime. `GetView` remains absent.

Resource Explorer is not a universal or authoritative inventory. Results are
limited to supported resource types, the selected view's filters and the
coverage of its existing indexes. Indexing and cross-Region replication are
eventually consistent: new resources can take minutes to appear, and initial
indexing or replication can take hours (AWS documents up to 36 hours in some
initial setup cases). Resource Explorer-owned indexes can return partial
results; a missing result does not prove that a resource does not exist. A
result only describes discovered metadata and does not grant permission to
access or modify the underlying resource.

## Cost and exposure

AWS Resource Explorer search has no additional per-call charge. A remote tool
call still uses the existing metered API Gateway request and Lambda execution.
Those remain protected by JWT, throttle 1/1, a 15-request tripwire, the
five-minute independent deadline and the default closed state. Enabling search
does not activate Resource Explorer or create billable infrastructure.

The original two-service inventory implementation and role change were deployed
while the API remained disabled and Lambda concurrency remained zero on
2026-09-03. The post-deployment
audit found exactly the two inventory statements, no managed policy, three
unchanged routes, no temporary alarm or schedule, and no collector invocation.
The separately authorized remote validation passed on 2026-09-07: two reads
returned seven Lambda functions and three API Gateway v2 APIs. Both services
reported success without truncation; write counters, warnings and errors were
zero. The window lasted about 35 seconds. Independent cleanup checks confirmed
API disabled, concurrency zero and no temporary alarm, schedule, OAuth directory
or Inspector process. Resource names and raw output are not retained as public
evidence. Future invocations still require an approved bounded window.

## Resource Explorer deployment evidence

DEV uses a dedicated unfiltered view in the `eu-west-1` aggregator index. The
aggregator currently receives the pre-existing local indexes from `eu-north-1`
and `us-east-1` in addition to `eu-west-1`; it is not presented as complete for
regions without a local index. The view includes no optional tag properties and
is not associated as the account default.

The reviewed DEV change set made no additions, deletions or replacements. Its
only effective application changes were the Lambda code, one environment value
and one inline statement granting `Search` on the dedicated view with exact
region and operation conditions. External integrations and WorkOS settings were
preserved.

Direct validation kept API Gateway disabled, temporarily enabled only the MCP
Lambda and installed an independent five-minute shutdown schedule. The MCP
catalog included `buscar_recursos_aws`; a query for Lambda resources returned
five sanitized results from one SDK request with zero external writes. The
structured audit record contains the tool name, normalized `ok` status and
bounded counters, but no query, ARN, account ID or result data. Cleanup restored
reserved concurrency zero and removed the schedule; the final audit found the
API disabled and no alarm or schedule.

## Evidence checked 2026-09-02

- https://docs.aws.amazon.com/lambda/latest/api/API_ListFunctions.html
- https://docs.aws.amazon.com/apigatewayv2/latest/api-reference/apis.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html
- https://docs.aws.amazon.com/resource-explorer/latest/apireference/API_Search.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_resource-explorer-2.html
- https://docs.aws.amazon.com/resource-explorer/latest/userguide/troubleshooting_search.html
- https://docs.aws.amazon.com/resource-explorer/latest/userguide/manage-service-check.html
- https://aws.amazon.com/resourceexplorer/pricing/
- https://aws.amazon.com/lambda/pricing/
- https://aws.amazon.com/api-gateway/pricing/
