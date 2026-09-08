# Threat model

## Scope and assets

The system is a single-user DEV MCP deployment in `eu-west-1`. The assets that
require protection are the AWS account, the Cognito identity, Telegram and
Trello credentials, confirmation tokens, provider destinations, audit integrity
and the project cost envelope.

Trust boundaries exist between the MCP client and API Gateway, API Gateway and
Lambda, Lambda and AWS control-plane APIs, Lambda and Parameter Store/DynamoDB,
and Lambda and each external provider. Local scripts and the GitHub repository
are separate administrative boundaries and never contain persistent provider
credentials.

## Threats and controls

| Threat | Primary controls | Residual risk |
| --- | --- | --- |
| Anonymous or incorrectly scoped access | Disabled endpoint by default; Cognito authorization code with PKCE and TOTP; exact issuer, audience, access-token type and resource scope checked at the gateway and Lambda | A compromised authenticated administrator session can act during an approved open window |
| Replay or alteration of a write request | Short-lived confirmation bound to caller, tool, normalized arguments and expiry; DynamoDB conditional single-use consumption | A provider may accept a request while its response is lost; execution is deliberately not retried |
| Credential disclosure | Standard SecureString, exact `ssm:GetParameter` resource, no secrets in source, logs or evidence; sanitized provider errors | The runtime must decrypt credentials briefly in memory to call the provider |
| Excessive AWS discovery | Fixed region, two allowlisted read operations, no pagination, ten results per service and one SDK attempt | Returned inventory is intentionally incomplete when the bound is reached |
| Denial of service or unexpected spend | API and compute closed normally; 1/1 stage throttle; 15-request alarm; five-minute independent shutdown; 10-second Lambda timeout; DynamoDB 1/1 maxima; $1 budget warning from $0.01 | AWS throttles and budgets are not contractual hard spending caps |
| Privilege escalation from Lambda | Dedicated execution roles, inline resource-specific policies and no attached managed policies | `lambda:ListFunctions` requires wildcard resource scope, constrained to the deployment region |
| Sensitive audit data | Fixed allowlisted schema; caller pseudonym; codes instead of messages; seven-day retention; logging failure cannot change tool results | CloudWatch operators can observe timing, tool names and normalized outcomes |
| Cleanup failure | API disabled before compute shutdown, independent Scheduler deadline, volume alarm and `finally` cleanup paths | A simultaneous AWS control-plane outage can delay cleanup until service recovery |
| Supply-chain regression | Locked dependencies, pinned CI actions, formatting, static typing, 170 offline tests and SAM build validation | Upstream package or action compromise cannot be eliminated entirely |

## Security assumptions

- The AWS and GitHub administrator accounts use appropriate account-level
  protection outside this repository.
- Only the designated administrator is created in the Cognito user pool.
- Telegram and Trello enforce their own credential and destination security.
- Opening DEV, changing infrastructure or performing a provider write remains a
  deliberate operational action.

## Non-goals

The deployment is not a multi-tenant service, a continuously available public
endpoint or a global AWS inventory product. PROD exists as an empty, closed
environment; live PROD validation and automated delivery remain out of scope.
