# Repository working agreement

## Product direction

`aws-remote-mcp` is an independently designed portfolio project: a secure,
cost-aware remote Model Context Protocol server on AWS. Public code,
documentation, pull requests and release notes describe product decisions,
engineering outcomes and original technical reasoning.

The service targets API Gateway, Lambda and current Streamable HTTP. It will
provide safe AWS inventory plus explicitly controlled Telegram and Trello
actions. Lambda/API Gateway remain the default unless evidence proves them
technically unsuitable.

## Engineering workflow

- Branch from `develop`; promote reviewed releases from `develop` to `main`.
- Use descriptive feature branches and small commits.
- Require green formatting, lint, strict typing, compilation, tests and SAM
  validation/build before merge.
- Keep ordinary CI offline and free of live AWS or third-party dependencies.
- Update `ROADMAP.md`, `docs/project-status.md` and decision records when the
  architecture or operational state changes.

## Operational approvals

Cost-bearing infrastructure, broader IAM, real credentials, external writes,
production activation, automatic deployment and destructive operations require
an explicit impact review before execution. Prepare and test safe changes first,
then report exact resources, IAM, exposure, cost and rollback. Never infer
approval from earlier unrelated work.

## Security and cost baseline

- Zero accidental cost is the primary operating rule.
- Use least privilege; never attach blanket administrator or read-only policies.
- Keep traffic, retries, output and execution time bounded.
- Treat API throttling and AWS Budgets as best-effort/delayed controls, not hard
  financial limits.
- Never commit or log secrets, account IDs, credentials, tokens, private
  destinations, raw sensitive AWS responses or credential-bearing URLs.
- The inbound MCP token authenticates only this resource and is never forwarded
  to AWS, Telegram or Trello.
- External writes use scoped, short-lived, single-use confirmation and no blind
  retries.
- DEV and PROD use separate stacks, configuration and credentials.

## Protocol and authentication

Use the current official MCP specification and Python SDK. Remote transport is
modern Streamable HTTP with real MCP semantics, not an MCP-like REST imitation.
The final endpoint must use standards-aligned OAuth/OIDC bearer authorization,
audience validation, correct 401/403 behavior and protected-resource metadata.

## AWS defaults

- Region: `eu-west-1`.
- Compute: Lambda + API Gateway HTTP API.
- IaC: SAM/CloudFormation.
- Observability: bounded structured CloudWatch logs with finite retention.
- Unknown or potentially billable AWS operations fail closed until classified.
- Avoid VPC, NAT, WAF, provisioned concurrency, databases and other persistent
  cost unless a documented requirement and explicit approval justify them.
