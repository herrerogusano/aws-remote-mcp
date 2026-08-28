# AWS Remote MCP

Exercise 5 of an AWS developer portfolio: a production-shaped, authenticated
remote Model Context Protocol server designed for AWS Lambda and API Gateway.

The project is currently in its foundation phase. It has a reproducible Python
environment and CI, but it does not deploy resources or call AWS or external
services yet.

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
