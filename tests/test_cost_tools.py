"""Cost Explorer ToolService confirmation and billable-call contracts."""

from __future__ import annotations

from typing import Any

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.adapters.protocols import AwsAdapterResult
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.core.cost_quota import (
    CostRequestLimiter,
    InMemoryCostRequestLimiter,
)
from aws_remote_mcp.core.models import CallerContext
from aws_remote_mcp.core.operations import build_default_registry
from aws_remote_mcp.services.tools import ToolService

BILLING_VIEW_ARN = "arn:aws:billing::123456789012:billingview/primary"


class FakeCostExplorerAdapter:
    billing_view_arn = BILLING_VIEW_ARN

    def __init__(self, result: AwsAdapterResult | None = None) -> None:
        self.calls: list[Any] = []
        self.result = result or AwsAdapterResult(
            data={"region": "us-east-1", "read_only": True},
            sdk_requests=1,
            resources=2,
        )

    def get_cost_and_usage(self, query: Any) -> AwsAdapterResult:
        self.calls.append(query)
        return self.result


def build_service(
    ce: FakeCostExplorerAdapter | None = None,
    *,
    limiter: CostRequestLimiter | None = None,
    without_limiter: bool = False,
) -> tuple[ToolService, FakeCostExplorerAdapter, CallerContext]:
    ce = ce or FakeCostExplorerAdapter()
    return (
        ToolService(
            operations=build_default_registry(),
            confirmations=ConfirmationGuard(),
            aws=FakeAwsAdapter(),
            aws_cost_explorer=ce,
            cost_request_limiter=(
                None if without_limiter else limiter or InMemoryCostRequestLimiter()
            ),
            telegram=FakeTelegramAdapter(),
            trello=FakeTrelloAdapter(),
            telegram_destinations=frozenset({"test-chat"}),
            trello_destinations=frozenset({("test-board", "test-list")}),
        ),
        ce,
        CallerContext("https://issuer.example", "caller-1"),
    )


ARGS = {
    "start_date": "2026-01-01",
    "end_date": "2026-01-02",
    "granularity": "DAILY",
    "group_by": "SERVICE",
}


def test_prepare_cost_query_makes_no_sdk_call_and_shows_capped_preview() -> None:
    service, ce, caller = build_service()

    result = service.prepare_aws_cost_query(caller, **ARGS)

    assert result.status == "confirmation_required"
    assert ce.calls == []
    assert result.confirmation is not None
    assert result.confirmation.action == "aws.cost_explorer.get_cost_and_usage"
    assert result.confirmation.expires_at.endswith("+00:00")
    assert result.data["preview"] == {
        "time_period": {"start": "2026-01-01", "end": "2026-01-02"},
        "granularity": "DAILY",
        "group_by": "SERVICE",
        "metric": "UnblendedCost",
        "currency": "USD",
        "max_cost_usd": "0.01",
        "max_api_requests": 1,
        "monthly_request_limit": 3,
        "monthly_max_api_cost_usd": "0.03",
        "read_only": True,
    }
    assert BILLING_VIEW_ARN not in str(result)


def test_execute_requires_exact_single_use_confirmation_and_calls_once() -> None:
    service, ce, caller = build_service()
    prepared = service.prepare_aws_cost_query(caller, **ARGS)
    assert prepared.confirmation is not None
    token = prepared.confirmation.token

    result = service.execute_aws_cost_query(caller, token, **ARGS)
    replay = service.execute_aws_cost_query(caller, token, **ARGS)

    assert result.status == "ok"
    assert result.counters.sdk_requests == 1
    assert result.counters.external_writes_attempted == 0
    assert len(ce.calls) == 1
    assert replay.errors[0].code == "confirmation_replayed"
    assert len(ce.calls) == 1


def test_payload_mutation_is_rejected_before_cost_explorer_call() -> None:
    service, ce, caller = build_service()
    prepared = service.prepare_aws_cost_query(caller, **ARGS)
    assert prepared.confirmation is not None

    changed = dict(ARGS, group_by="REGION")
    result = service.execute_aws_cost_query(
        caller, prepared.confirmation.token, **changed
    )

    assert result.status == "error"
    assert result.errors[0].code == "confirmation_payload_mismatch"
    assert ce.calls == []


def test_invalid_cost_query_is_rejected_before_confirmation_or_sdk_call() -> None:
    service, ce, caller = build_service()

    result = service.prepare_aws_cost_query(
        caller,
        start_date="2026-01-01",
        end_date="2026-02-02",
        granularity="DAILY",
        group_by="SERVICE",
    )

    assert result.status == "error"
    assert result.errors[0].code == "cost_period_too_long"
    assert ce.calls == []


def test_monthly_limit_blocks_fourth_fresh_confirmation_before_sdk_call() -> None:
    service, ce, caller = build_service()

    results = []
    for _ in range(4):
        prepared = service.prepare_aws_cost_query(caller, **ARGS)
        assert prepared.confirmation is not None
        results.append(
            service.execute_aws_cost_query(
                caller,
                prepared.confirmation.token,
                **ARGS,
            )
        )

    assert [result.status for result in results] == ["ok", "ok", "ok", "error"]
    assert results[-1].errors[0].code == "cost_monthly_limit_exceeded"
    assert results[-1].counters.sdk_requests == 0
    assert len(ce.calls) == 3


def test_missing_monthly_limiter_fails_closed_before_sdk_call() -> None:
    service, ce, caller = build_service(without_limiter=True)
    prepared = service.prepare_aws_cost_query(caller, **ARGS)
    assert prepared.confirmation is not None

    result = service.execute_aws_cost_query(
        caller,
        prepared.confirmation.token,
        **ARGS,
    )

    assert result.status == "error"
    assert result.errors[0].code == "cost_quota_unavailable"
    assert result.counters.sdk_requests == 0
    assert ce.calls == []
