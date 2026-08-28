# AWS Remote MCP

Exercise 5 of an AWS developer portfolio: a production-shaped, authenticated
remote Model Context Protocol server designed for AWS Lambda and API Gateway.

The project currently exposes a local-only MCP server over current Streamable
HTTP. All AWS data is synthetic and Telegram/Trello tools are preview-only; it
does not deploy resources or call AWS or external services yet.

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

No execute/send/create tool is exposed in this phase.

## Branch and environment model

```text
phase/* -> develop -> DEV
              |
              +---- promotion PR -> main -> PROD
```

The environments are mandatory, but no AWS environment exists yet. Deployment
actions remain subject to the approval gates in `docs/plan/GATES.md`.

## Safety baseline

- No live AWS, Telegram, Trello, OAuth, or paid-service calls in normal CI.
- No secrets or persistent credentials in source control.
- No AWS deployment before Gate A approval.
- Future tool calls must use structured audit logging and bounded traffic.

See `PLAN.md` and `docs/plan/PROGRESS.md` for the full roadmap and current state.
