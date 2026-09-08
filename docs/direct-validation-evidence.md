# Direct Lambda validation evidence

Date: 2026-08-28  
Region: `eu-west-1`

## Scope

The deployed MCP Lambda was invoked directly three times while the API Gateway
default endpoint remained disabled. Before concurrency zero was removed, an
independent five-minute Scheduler deadline was installed. The local `finally`
path then restored concurrency zero, reaffirmed the disabled API and deleted the
temporary schedule.

No Cost Explorer query, API Gateway data request, real AWS inventory lookup or
external integration was used.

## Contract results

| Invocation | Result |
| --- | --- |
| `tools/list` | Exact tools: `diagnostico`, `listar_recursos_aws_sintetico` |
| `diagnostico` | `ok`, environment `dev`, no external side effects |
| `listar_recursos_aws_sintetico` | `ok`, bounded synthetic data only |

CloudWatch recorded HTTP application status `200` and Lambda platform status
`success` for all three invocations.

## Runtime evidence

| Execution | Duration | Billed duration | Initialization |
| --- | ---: | ---: | ---: |
| Cold | 1,022 ms | 3,172 ms | 2,150 ms |
| Warm 1 | 133 ms | 133 ms | — |
| Warm 2 | 89 ms | 90 ms | — |

Maximum memory used was 108 MB of the configured 128 MB. Total billed compute
was 0.424 GB-seconds. Using the public first-tier x86 Lambda price and ignoring
the free tier, the three Lambda requests plus compute are below `$0.00001`.
Small CloudWatch log ingestion and storage are separate.

## Verified closing state

- CloudFormation stack: `CREATE_COMPLETE`;
- API default endpoint disabled: `true`;
- MCP Lambda reserved concurrency: `0`;
- temporary request alarm count: `0`;
- automatic-close schedule count: `0`.

## Final structured-audit validation

Date: 2026-09-09
Region: `eu-west-1`

The merged `develop` revision was deployed to the existing DEV stack with the
external-integration profile preserved. CloudFormation completed with
`UPDATE_COMPLETE` and no resource replacement. A direct validation then made
only three bounded Lambda invocations while API Gateway remained disabled:

| Operation | Result |
| --- | --- |
| `tools/list` | Exact six-tool integration profile |
| `diagnostico` | `ok`, DEV, no external side effects |
| `listar_inventario_aws` | Two reads, at most 20 resources, zero writes |

The external execute tools were not called, so this validation sent no Telegram
message and created no Trello card. CloudWatch contained one
`mcp_tool_result` record for each called tool. Both records used schema version
one and contained exactly the allowlisted context, status, issue-code and counter
fields; no arguments, result data, confirmation material or provider identifiers
were present.

The post-validation audit confirmed API disablement, Lambda reserved concurrency
zero, no active alarm and no active shutdown schedule. The confirmation table
remained active with encryption, TTL and one-read/one-write on-demand maximums.

This evidence validates the deployed Lambda/MCP boundary. It deliberately does
not claim that the API Gateway IAM data path has been validated.

## Pricing source

- https://aws.amazon.com/lambda/pricing/

## Confirmed external integration validation

Date: 2026-09-08  
Region: `eu-west-1`

The opt-in DEV integration profile was validated through direct Lambda
invocation while API Gateway remained disabled. A five-minute independent
Scheduler deadline was installed before removing concurrency zero, and the
local `finally` path restored every shutdown invariant.

The first execution exposed a DynamoDB expression error: the application field
`consumed` was not mapped through `ExpressionAttributeNames`. The conditional
update failed before the provider boundary, the confirmation remained
unconsumed and no Telegram request was attempted. The expression and its
regression coverage were corrected and deployed in closed state before a new
validation.

The successful execution performed seven bounded invocations:

| Operation | Result |
| --- | --- |
| `tools/list` | Exact six-tool integration profile |
| `diagnostico` | `ok`, DEV, no external side effects |
| `listar_inventario_aws` | Two reads, at most 20 resources, zero writes |
| Telegram prepare | Exact destination and payload confirmation issued |
| Telegram execute | One confirmation consumed; one provider write succeeded |
| Trello prepare | Exact board/list and payload confirmation issued |
| Trello execute | One confirmation consumed; one provider write succeeded |

The audit immediately afterward found two consumed confirmation records and one
unconsumed record from the pre-provider failure. The latter is left to normal
TTL deletion. No raw confirmation, provider credential, destination identifier,
account identifier or provider response was recorded as evidence.

Verified closing state:

- CloudFormation stack: `UPDATE_COMPLETE`;
- API default endpoint disabled: `true` throughout;
- MCP Lambda reserved concurrency: `0` after validation;
- temporary request alarm count: `0`;
- automatic-close schedule count: `0`.
