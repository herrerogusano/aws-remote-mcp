# Cost safety model

Checked 2026-08-28 for the account and `eu-west-1`.

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
- AWS IAM authorization is mandatory;
- MCP Lambda reserved concurrency is zero;
- the internal shutdown Lambda has no HTTP trigger and can only be invoked by
  the exact safety topic or dedicated Scheduler role;
- no recurring alarm or schedule exists;
- idle Lambda, IAM and SNS resources have no fixed hourly charge.

Opening a window requires all of these checks in order:

1. A one-time AWS-side shutdown is created in a dedicated schedule group and
   auto-deletes afterward.
2. A temporary alarm is armed at 20 API requests in one minute.
3. Lambda concurrency becomes one.
4. Only then is the default API endpoint enabled, for at most five minutes.

The close path disables the API before stopping Lambda and attempts all cleanup
actions even if one fails. Manual closure and the independent AWS-side deadline
are redundant.

At 128 MB, one continuously busy Lambda for five minutes consumes at most 37.5
GB-seconds, approximately $0.000625 at the published first-tier example rate,
before any free tier. At the configured API target, five minutes is roughly 300
requests ($0.0003 at $1/million), while the alarm should close substantially
earlier. These are estimates, not billing guarantees.

## Controls intentionally not used

- API Gateway regional account throttling is shared with another existing API
  and is not reduced account-wide.
- AWS WAF and custom domains add fixed monthly cost and are unnecessary while the
  endpoint is disabled outside a five-minute signed test.
- Provisioned concurrency, VPC and NAT are prohibited because they add idle cost.
- The Cost Explorer API is not called by scripts or runtime controls: each primary
  billing-view request costs $0.01 and current-month data can be delayed by about
  24 hours. Existing AWS Budget email notifications provide the account warning.

## Sources

- https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html
- https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html
- https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/
- https://aws.amazon.com/api-gateway/pricing/
- https://aws.amazon.com/lambda/pricing/
