# AWS Remote MCP

A production-shaped, authenticated remote Model Context Protocol server designed
for AWS Lambda and API Gateway.

The project exposes a local MCP server over current Streamable HTTP and has a
closed-by-default DEV foundation deployed in AWS. The application includes a
bounded, read-only AWS inventory adapter plus confirmed Telegram and Trello
actions backed by persistent single-use state. Their opt-in DEV profile has been
validated by direct Lambda invocation while the public endpoint remained closed;
the endpoint and its compute stay disabled outside separately approved windows.

## Development

Requirements:

- Python 3.13
- [uv](https://docs.astral.sh/uv/)

Install the locked environment and run the same checks as CI:

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
sam validate --lint --region eu-west-1
sam build --beta-features
```

Run the local server:

```bash
uv run aws-remote-mcp
```

It binds only to `127.0.0.1:8000` and exposes the single MCP endpoint at
`http://127.0.0.1:8000/mcp`. The transport is stateless and uses JSON responses.
Current-protocol clients can discover and call:

- `diagnostico`
- `listar_inventario_aws`
- `preparar_mensaje_telegram`
- `preparar_tarjeta_trello`

Local development returns a deterministic fixture for AWS inventory and never
contacts AWS. Execute/send/create tools remain excluded from the default local
profile and are exposed remotely only by the explicitly enabled integration
profile documented in `docs/external-integrations.md`.

## Branch and environment model

```text
feature/* -> develop -> DEV
              |
              +---- promotion PR -> main -> PROD
```

The DEV environment exists in AWS and remains closed by default; PROD does not
exist. Infrastructure changes require the review described in
`docs/operational-approvals.md`.

The prepared DEV stack is closed by default: its execute-api endpoint is disabled,
the MCP route requires a scoped, audience-bound Cognito JWT, and MCP Lambda
concurrency is zero. A separately approved test window is limited to five minutes
with an independent scheduled shutdown and request-volume tripwire. See
`docs/cost-safety.md`.

The deployed Lambda contract, including one confirmed Telegram message and one
confirmed Trello card, has also been validated directly while the API remained
disabled. See `docs/direct-validation-evidence.md` and
`docs/external-integrations.md`.

The selected OAuth/OIDC profile and its deployed single-user Cognito foundation
are documented in `docs/oauth-provider-evaluation.md` and
`docs/auth-deployment-runbook.md`. TOTP and JWT route integration are complete;
any remote opening remains a separate gated action.

The deployed closed DEV inventory implementation permits only one non-paginated
`ListFunctions` request and one non-paginated API Gateway v2 `GetApis` request,
with ten results per service and no SDK retries. Real validation passed on
2026-09-07 with two reads, ten resources and no writes; DEV was closed afterward.
See `docs/aws-inventory.md`.

## Safety baseline

- No live AWS, Telegram, Trello, OAuth, or paid-service calls in normal CI.
- No secrets or persistent credentials in source control.
- No AWS deployment without explicit infrastructure approval.
- Future tool calls must use structured audit logging and bounded traffic.

See `ROADMAP.md` and `docs/project-status.md` for the roadmap and current state.
The prepared DEV procedure is in `docs/deployment-runbook.md`; explicit approval
is mandatory before executing it.
