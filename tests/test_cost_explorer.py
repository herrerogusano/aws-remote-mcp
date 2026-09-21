"""Offline validation and confirmation contracts for Cost Explorer."""

from __future__ import annotations

import pytest

from aws_remote_mcp.adapters.aws_cost_explorer import AwsCostExplorerAdapter
from aws_remote_mcp.core.cost_query import (
    COST_EXPLORER_METRIC,
    CostQueryValidationError,
    validate_cost_explorer_query,
)

BILLING_VIEW_ARN = "arn:aws:billing::123456789012:billingview/primary"


class FakeCostExplorerClient:
    def __init__(
        self, response: dict[str, object], failure: Exception | None = None
    ) -> None:
        self.response = response
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def get_cost_and_usage(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return self.response


def build_cost_adapter(
    client: FakeCostExplorerClient,
) -> tuple[AwsCostExplorerAdapter, list[tuple[str, str]]]:
    created: list[tuple[str, str]] = []

    def factory(service: str, region: str) -> FakeCostExplorerClient:
        created.append((service, region))
        return client

    return (
        AwsCostExplorerAdapter(
            billing_view_arn=BILLING_VIEW_ARN, client_factory=factory
        ),
        created,
    )


def cost_response(
    *, total: object = None, keys: list[str] | None = None
) -> dict[str, object]:
    if total is None:
        total = {COST_EXPLORER_METRIC: {"Amount": "2.5000", "Unit": "USD"}}
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
                "Total": total,
                "Groups": [
                    {
                        "Keys": keys or ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            COST_EXPLORER_METRIC: {
                                "Amount": "2.5000",
                                "Unit": "USD",
                            }
                        },
                        "RawProviderField": "must-not-leak",
                    }
                ],
            }
        ],
        "NextPageToken": "next-page-secret",
        "BillingViewArn": BILLING_VIEW_ARN,
        "AccountId": "123456789012",
        "Arn": "arn:aws:ce:us-east-1:123456789012:private",
    }


def test_cost_query_accepts_fixed_dimensions_and_31_day_exclusive_window() -> None:
    query = validate_cost_explorer_query("2026-01-01", "2026-02-01", "DAILY", "SERVICE")

    assert query.start_date == "2026-01-01"
    assert query.end_date == "2026-02-01"
    assert query.granularity == "DAILY"
    assert query.group_by == "SERVICE"


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2026-01-01", "2026-02-02"),
        ("2026-01-01", "2026-01-01"),
        ("2026-01-02", "2026-01-01"),
    ],
)
def test_cost_query_rejects_long_empty_or_reversed_periods(
    start_date: str, end_date: str
) -> None:
    with pytest.raises(CostQueryValidationError):
        validate_cost_explorer_query(start_date, end_date, "DAILY", "SERVICE")


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("2026-1-01", "2026-01-02"),
        ("2026-01-01T00:00:00Z", "2026-01-02"),
        ("not-a-date", "2026-01-02"),
        ("2026-02-30", "2026-03-01"),
        ("2026-01-01", "2026-02-31"),
    ],
)
def test_cost_query_requires_exact_valid_iso_calendar_dates(
    start_date: str, end_date: str
) -> None:
    with pytest.raises(CostQueryValidationError):
        validate_cost_explorer_query(start_date, end_date, "DAILY", "SERVICE")


@pytest.mark.parametrize("granularity", ["HOURLY", "daily", "", None, 1])
def test_cost_query_rejects_non_allowlisted_granularity(granularity: object) -> None:
    with pytest.raises(CostQueryValidationError):
        validate_cost_explorer_query("2026-01-01", "2026-01-02", granularity, "SERVICE")


@pytest.mark.parametrize(
    "group_by",
    ["ACCOUNT", "TAG", "SERVICE,REGION", "service", "", None, ["SERVICE"]],
)
def test_cost_query_rejects_filters_tags_and_extra_group_dimensions(
    group_by: object,
) -> None:
    with pytest.raises(CostQueryValidationError):
        validate_cost_explorer_query("2026-01-01", "2026-01-02", "MONTHLY", group_by)


def test_adapter_makes_one_us_east_1_call_with_fixed_metric_and_view() -> None:
    client = FakeCostExplorerClient(cost_response())
    adapter, created = build_cost_adapter(client)
    query = validate_cost_explorer_query("2026-01-01", "2026-01-02", "DAILY", "SERVICE")

    result = adapter.get_cost_and_usage(query)

    assert result.status == "ok"
    assert result.sdk_requests == 1
    assert created == [("ce", "us-east-1")]
    assert len(client.calls) == 1
    assert client.calls[0] == {
        "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        "BillingViewArn": BILLING_VIEW_ARN,
    }
    assert result.data["truncated"] is True
    assert result.data["returned_periods"] == 1
    assert result.data["returned_groups"] == 1
    serialized = str(result)
    for secret in (
        BILLING_VIEW_ARN,
        "next-page-secret",
        "123456789012",
        "must-not-leak",
    ):
        assert secret not in serialized


def test_adapter_allows_missing_total_when_group_rows_are_valid() -> None:
    client = FakeCostExplorerClient(cost_response(total={}))
    adapter, _ = build_cost_adapter(client)
    query = validate_cost_explorer_query(
        "2026-01-01", "2026-01-02", "MONTHLY", "REGION"
    )

    result = adapter.get_cost_and_usage(query)

    assert result.status == "ok"
    assert result.resources == 1
    periods = result.data["results_by_time"]
    assert isinstance(periods, list)
    first_period = periods[0]
    assert isinstance(first_period, dict)
    assert first_period["total_usd"] is None


@pytest.mark.parametrize(
    "response",
    [{}, {"ResultsByTime": None}, {"ResultsByTime": "invalid"}],
)
def test_adapter_rejects_invalid_top_level_response(
    response: dict[str, object],
) -> None:
    client = FakeCostExplorerClient(response)
    adapter, created = build_cost_adapter(client)
    query = validate_cost_explorer_query("2026-01-01", "2026-01-02", "DAILY", "SERVICE")

    result = adapter.get_cost_and_usage(query)

    assert result.status == "error"
    assert result.sdk_requests == 1
    assert result.resources == 0
    assert created == [("ce", "us-east-1")]


def test_adapter_sanitizes_sdk_failures_and_never_retries() -> None:
    client = FakeCostExplorerClient(
        {}, RuntimeError("account=123456789012 secret=must-not-leak")
    )
    adapter, created = build_cost_adapter(client)
    query = validate_cost_explorer_query("2026-01-01", "2026-01-02", "DAILY", "SERVICE")

    result = adapter.get_cost_and_usage(query)

    assert result.status == "error"
    assert result.sdk_requests == 1
    assert result.resources == 0
    assert len(client.calls) == 1
    assert created == [("ce", "us-east-1")]
    assert "must-not-leak" not in str(result)
    assert "123456789012" not in str(result)


def test_adapter_invalid_billing_view_arn_fails_at_construction() -> None:
    with pytest.raises(ValueError):
        AwsCostExplorerAdapter(billing_view_arn="arn:aws:ce:private")
