# AWS Remote MCP

A production-shaped, authenticated remote Model Context Protocol server designed
for AWS Lambda and API Gateway.

The project exposes a local MCP server over current Streamable HTTP and has a
closed-by-default DEV foundation deployed in AWS. All application AWS data is
synthetic and Telegram/Trello tools are preview-only; the remote endpoint and
its compute remain disabled outside a separately approved validation window.

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
- `listar_recursos_aws_sintetico`
- `preparar_mensaje_telegram`
- `preparar_tarjeta_trello`

No execute/send/create tool is exposed in the current development build.

## Branch and environment model

```text
feature/* -> develop -> DEV
              |
              +---- promotion PR -> main -> PROD
```

The environments are mandatory, but no project AWS environment exists yet.
Infrastructure changes require the review described in
`docs/operational-approvals.md`.

The prepared DEV stack is closed by default: its execute-api endpoint is disabled,
the route requires AWS IAM, and MCP Lambda concurrency is zero. A separately
approved test window is limited to five minutes with an independent scheduled
shutdown and request-volume tripwire. See `docs/cost-safety.md`.

## Safety baseline

- No live AWS, Telegram, Trello, OAuth, or paid-service calls in normal CI.
- No secrets or persistent credentials in source control.
- No AWS deployment without explicit infrastructure approval.
- Future tool calls must use structured audit logging and bounded traffic.

See `ROADMAP.md` and `docs/project-status.md` for the roadmap and current state.
The prepared DEV procedure is in `docs/deployment-runbook.md`; explicit approval
is mandatory before executing it.
