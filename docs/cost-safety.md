# Cost safety model

Checked 2026-09-08 for the account and `eu-west-1`.

## Account control

The account already has a monthly $1 cost budget with two email subscribers and
an actual-spend notification above $0.01. It has no automatic Budget Action.
AWS documents that cost data and Budget notifications can be delayed, so this is
an early warning rather than a hard monthly spending cap.

AWS has no account setting that guarantees a bill can never exceed a chosen
amount. Budget Actions can restrict selected IAM activity but cannot retroactively
remove cost or reliably stop every already-running service. No IAM lockout action
is added to the personal account.

## Project controls

Outside a test window:

- the API default endpoint is disabled;
- Cognito JWT authorization with an exact audience and scope is mandatory on the
  MCP route;
- MCP Lambda reserved concurrency is zero;
- the internal shutdown Lambda has no HTTP trigger and can only be invoked by
  the exact safety topic or dedicated Scheduler role;
- no recurring alarm or schedule exists;
- idle Lambda, IAM and SNS resources have no fixed hourly charge.

Opening a window requires all of these checks in order:

1. A one-time AWS-side shutdown is created in a dedicated schedule group and
   auto-deletes afterward.
2. A temporary alarm is armed at 15 API requests in one minute.
3. Lambda is enabled. Reserved concurrency one is preferred; the reviewed
   Inspector fallback permits only the regional account cap of exactly 10 when
   AWS's reduced-account quota cannot allocate a reservation.
4. Only then is the default API endpoint enabled, for at most five minutes.

The close path disables the API before stopping Lambda and attempts all cleanup
actions even if one fails. Manual closure and the independent AWS-side deadline
are redundant.

The prepared AWS inventory tool adds exactly two control-plane reads per tool
call: one Lambda `ListFunctions` and one API Gateway v2 `GetApis`. It does not
paginate and configures total SDK attempts to one, so an Inspector validation
performs two downstream reads, not an unbounded scan. AWS documents Lambda
charges for function invocations/duration and API Gateway charges for calls
received by hosted APIs; no separate per-request price is documented for these
two management reads. The enclosing API Gateway request and Lambda execution
remain part of the existing bounded-window estimate.

The separate Resource Explorer search capability, when explicitly enabled,
makes one non-paginated `Search` request per tool call and returns at most 50
matches. AWS offers Resource Explorer search at no additional charge. The MCP
request still uses the same metered API Gateway and Lambda path already counted
in the bounded-window estimate. Its view ARN is empty by default; supplying one
does not create or enable Resource Explorer, indexes, views, or other persistent
infrastructure. The Lambda role receives only `Search` on that exact existing
view, so no setup or indexing permissions are added.

## Cost Explorer opt-in

Cost Explorer is disabled by default. `EnableCostExplorer=false` hides its tools,
omits Cost Explorer IAM, and does not activate or configure the AWS service. If
separately approved and enabled, the role gets only `ce:GetCostAndUsage` on the
account's `primary` billing view ARN; the Lambda receives that same value as
`COST_EXPLORER_BILLING_VIEW_ARN`. A single-use confirmation gates each execution.
The runtime contract is exactly one SDK request, one result page, no
pagination and no automatic retry; a `NextPageToken` is not followed. The
confirmation itself is not a Cost Explorer API request; each API request (each
page in a paginated query) costs $0.01.

Before the billable call, DynamoDB atomically consumes one of three global slots
for the current UTC month. A failed downstream attempt still consumes its slot;
the fourth attempt, missing quota state or a DynamoDB error fails closed before
AWS. This caps Cost Explorer API requests initiated by this MCP at `$0.03` per
month while the table remains intact. It does not cap unrelated AWS credentials,
administrator actions or other services. No Cost Explorer call is made during
template validation, deployment, or the ordinary closed-stack procedure. The
current PROD profile must keep `EnableCostExplorer=false`.

Cost Explorer data is delayed rather than live. AWS says current-month data is
typically available after about 24 hours, with historical and forecast data
taking longer; upstream billing changes can arrive later. Do not present this
tool as a real-time spend monitor or a way to enforce a budget. AWS also states
that Cost Explorer cannot be disabled after account-level activation. Any such
activation is a separate account-level decision and is not performed by this
project's template or runtime.

## Cost envelopes

The deployed controls produce three materially different envelopes:

| State | Bounded AWS activity | Conservative incremental cost |
| --- | --- | --- |
| Closed (normal state) | API rejects execution and Lambda concurrency is zero | No request or compute cost; only negligible retained log/table storage and the Cognito active-user charge described below |
| Expected validation | A small, manually selected set of authenticated calls before immediate closure | A fraction of one cent, normally covered by service free tiers |
| Five-minute deadline | At most about 300 requests at the stage target of one request per second | About $0.0068 before free tiers if every invocation consumes the full ten-second Lambda timeout |

The deadline calculation deliberately assumes the least favourable execution
duration: 300 invocations x 10 seconds x 0.125 GB = 375 GB-seconds. At AWS's
published first-tier Lambda example rate this is about $0.00625, plus about
$0.00006 for Lambda requests and roughly $0.0003 for HTTP API calls at the
representative $1-per-million tier. The temporary 15-request alarm is intended
to close the window far earlier, but it is not used to make the five-minute
bound look smaller. Free-tier allowances are also excluded from the estimate.

The stage rate and burst targets are throttling controls, not contractual hard
quotas: AWS documents that throttling is best effort. The independent five-minute
shutdown and Lambda's ten-second timeout therefore remain the stronger time and
per-execution limits. Likewise, the DynamoDB one-read/two-write maximums are
cost-control targets and may briefly admit burst capacity. Even if each of the
roughly 300 admitted calls used one read and two writes, that request volume is
far below one cent at public per-million request pricing.

The optional external-integration profile is off by default. When enabled it
uses one DynamoDB on-demand table for confirmation state, with table maximums of
one read request unit and two write request units per second, no indexes, no
streams and no point-in-time recovery. DynamoDB documents these maximums as
cost-control targets rather than absolute ceilings because burst capacity can
temporarily exceed them. Confirmation records expire after five minutes and TTL
removes them asynchronously.

Provider credentials use one Parameter Store Standard SecureString under the
AWS-managed `aws/ssm` key. Standard parameters and standard-throughput API
interactions have no additional charge, and AWS-managed KMS keys have no key or
request charge. Secrets Manager and customer-managed KMS keys are intentionally
excluded because they add recurring charges. Each confirmed execution performs
at most one Parameter Store read, one DynamoDB conditional write and one provider
POST; failed confirmation checks may add one strongly consistent DynamoDB read.

Cognito Plus has no fixed project minimum. With the single administrator being
the only monthly active user, its known recurring application charge is $0.02
for a month in which that user is active. Repeated requests from the same user do
not create additional monthly active users.

CloudWatch application logs expire after seven days. The alarm and Scheduler
deadline exist only during an opening window and are removed by closure. The SNS
topic, Lambda functions, API definition, IAM roles and Scheduler group do not
generate request/compute charges while idle.

## Controls intentionally not used

- API Gateway regional account throttling is shared with another existing API
  and is not reduced account-wide.
- AWS WAF and custom domains add fixed monthly cost and are unnecessary while the
  endpoint is disabled outside a five-minute signed test.
- Provisioned concurrency, VPC and NAT are prohibited because they add idle cost.
- Cost Explorer remains disabled by default and is excluded from deployment and
  validation scripts. If explicitly enabled, enforce a single-use confirmation,
  one request and one page per execution at $0.01, plus three global attempts
  per UTC month. Do not imply that this application quota or the AWS Budget
  email alert guarantees a maximum total AWS bill.
- Resource Explorer is never turned on or configured by the stack. Search stays
  disabled unless an existing `eu-west-1` view ARN is explicitly approved and
  supplied; PROD keeps the value empty.

## Sources

- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html
- https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html
- https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
- https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html
- https://docs.aws.amazon.com/cost-management/latest/userguide/bcm-lite-cost-explorer.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_ce.html
- https://docs.aws.amazon.com/cli/latest/reference/ce/get-cost-and-usage.html
- https://aws.amazon.com/api-gateway/pricing/
- https://aws.amazon.com/lambda/pricing/
- https://docs.aws.amazon.com/lambda/latest/api/API_ListFunctions.html
- https://docs.aws.amazon.com/apigatewayv2/latest/api-reference/apis.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_lambda.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_apigatewayv2.html
- https://docs.aws.amazon.com/resource-explorer/latest/apireference/API_Search.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_resource-explorer-2.html
- https://aws.amazon.com/resourceexplorer/pricing/
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode-max-throughput.html
- https://aws.amazon.com/dynamodb/pricing/
- https://aws.amazon.com/systems-manager/pricing/
- https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-startup-security-baseline/wkld-03.html
