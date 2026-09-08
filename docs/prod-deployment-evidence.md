# Closed PROD deployment evidence

Date: 2026-09-09

Region: `eu-west-1`

## Promotion

The complete reviewed implementation was promoted from `develop` to `main`
through pull request 34. Environment-neutral output aliases were subsequently
reviewed and promoted through pull request 36. Both promotion checks passed
before the corresponding PROD deployment.

## Isolated resources

PROD uses the separate CloudFormation stacks `aws-remote-mcp-prod` and
`aws-remote-mcp-auth-prod`. The application stack was created closed, the empty
PROD Cognito stack was bound to its new MCP URI, and the application was then
updated immediately to use only the PROD issuer, audience and scope.

No DEV identity or integration state was copied. PROD has:

- zero Cognito users;
- external integrations disabled;
- no confirmation table;
- no integration SecureString;
- no Telegram or Trello execution tools or credential permissions.

## Verified controls

| Control | Observed state |
| --- | --- |
| Application stack | `UPDATE_COMPLETE` |
| Authentication stack | `CREATE_COMPLETE` |
| API endpoint | Disabled |
| Lambda reserved concurrency | `0` |
| Lambda memory / timeout | 128 MB / 10 seconds |
| Stage throttle | Rate 1, burst 1 |
| MCP authorization | PROD JWT issuer, PROD endpoint audience and exact `/use` scope |
| Cognito | Plus, deletion protection active, threat protection enforced |
| User creation / MFA | Administrator-only, software-token MFA required |
| OAuth client | Public code-flow client, no secret, five-minute access token |
| Active traffic alarms | `0` |
| Active shutdown schedules | `0` |

The DEV endpoint remained disabled and its Lambda concurrency remained zero
throughout PROD creation. PROD Lambda and API Gateway were not invoked, and no
provider request or Cost Explorer query was made.

