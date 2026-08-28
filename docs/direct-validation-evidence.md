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

This evidence validates the deployed Lambda/MCP boundary. It deliberately does
not claim that the API Gateway IAM data path has been validated.

## Pricing source

- https://aws.amazon.com/lambda/pricing/
