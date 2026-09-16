"""Single-request, bounded adapter for explicitly confirmed Cost Explorer reads."""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from aws_remote_mcp.adapters.protocols import AdapterIssue, AwsAdapterResult
from aws_remote_mcp.core.cost_query import (
    COST_EXPLORER_MAX_COST_USD,
    COST_EXPLORER_METRIC,
    CostExplorerQuery,
    CostQueryValidationError,
    validate_cost_explorer_query,
)
from aws_remote_mcp.core.cost_quota import (
    MONTHLY_COST_REQUEST_LIMIT,
    MONTHLY_MAX_API_COST_USD,
)
from aws_remote_mcp.core.models import JsonValue

COST_EXPLORER_REGION = "us-east-1"
MAX_COST_PERIODS = 31
MAX_COST_GROUPS = 100
MAX_DIMENSION_VALUE_CHARS = 128
MAX_AMOUNT_CHARS = 64
_PRIMARY_BILLING_VIEW_ARN = re.compile(
    r"arn:aws(?:-[a-z0-9-]+)?:billing::\d{12}:billingview/primary\Z"
)
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_SAFE_DIMENSION_VALUE = re.compile(r"[^A-Za-z0-9 .:/_-]")

type CostExplorerClientFactory = Callable[[str, str], Any]


def _boto_client(service: str, region: str) -> Any:
    boto3 = importlib.import_module("boto3")
    config_module = importlib.import_module("botocore.config")
    config = config_module.Config(
        connect_timeout=2,
        read_timeout=5,
        retries={"total_max_attempts": 1, "mode": "standard"},
    )
    return boto3.client(service, region_name=region, config=config)


class AwsCostExplorerAdapter:
    """Make one `GetCostAndUsage` call in us-east-1 and never follow a page token."""

    def __init__(
        self,
        *,
        billing_view_arn: str,
        client_factory: CostExplorerClientFactory = _boto_client,
    ) -> None:
        if _PRIMARY_BILLING_VIEW_ARN.fullmatch(billing_view_arn) is None:
            raise ValueError("A primary Cost Explorer billing view ARN is required.")
        self._billing_view_arn = billing_view_arn
        self._client_factory = client_factory

    @property
    def billing_view_arn(self) -> str:
        return self._billing_view_arn

    def get_cost_and_usage(self, query: CostExplorerQuery) -> AwsAdapterResult:
        try:
            normalized = validate_cost_explorer_query(
                query.start_date,
                query.end_date,
                query.granularity,
                query.group_by,
            )
        except CostQueryValidationError as error:
            # This is an internal port, but maintain fail-closed behavior if a
            # caller bypasses ToolService and constructs an invalid query.
            return _failure(error.code, str(error), sdk_requests=0)

        try:
            client = self._client_factory("ce", COST_EXPLORER_REGION)
            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": normalized.start_date,
                    "End": normalized.end_date,
                },
                Granularity=normalized.granularity,
                Metrics=[COST_EXPLORER_METRIC],
                GroupBy=[
                    {"Type": "DIMENSION", "Key": normalized.group_by},
                ],
                BillingViewArn=self._billing_view_arn,
            )
        except Exception:
            return _failure(
                "cost_explorer_query_unavailable",
                "AWS Cost Explorer query could not be completed.",
                sdk_requests=1,
            )

        if not isinstance(response, Mapping):
            return _failure(
                "invalid_cost_explorer_response",
                "AWS Cost Explorer returned an invalid response.",
                sdk_requests=1,
            )
        raw_periods = response.get("ResultsByTime")
        if not isinstance(raw_periods, list):
            return _failure(
                "invalid_cost_explorer_response",
                "AWS Cost Explorer returned an invalid response.",
                sdk_requests=1,
            )

        sanitized_periods: list[JsonValue] = []
        group_count = 0
        malformed_count = 0
        clipped = bool(response.get("NextPageToken")) or len(raw_periods) > (
            MAX_COST_PERIODS
        )
        for raw_period in raw_periods[:MAX_COST_PERIODS]:
            if not isinstance(raw_period, Mapping):
                malformed_count += 1
                continue
            start = _safe_date(raw_period.get("TimePeriod"), "Start")
            end = _safe_date(raw_period.get("TimePeriod"), "End")
            if start is None or end is None:
                malformed_count += 1
                continue

            total_usd: str | None = None
            totals = raw_period.get("Total")
            if isinstance(totals, Mapping):
                if totals:
                    total_usd = _safe_amount(totals.get(COST_EXPLORER_METRIC))
            else:
                malformed_count += 1
            if isinstance(totals, Mapping) and totals and total_usd is None:
                malformed_count += 1

            raw_groups = raw_period.get("Groups", [])
            if not isinstance(raw_groups, list):
                malformed_count += 1
                raw_groups = []
            remaining = MAX_COST_GROUPS - group_count
            if len(raw_groups) > remaining:
                clipped = True
            groups: list[JsonValue] = []
            for raw_group in raw_groups[:remaining]:
                group = _sanitize_group(raw_group, normalized.group_by)
                if group is None:
                    malformed_count += 1
                    continue
                groups.append(group)
                group_count += 1
            sanitized_periods.append(
                {
                    "start": start,
                    "end": end,
                    "total_usd": total_usd,
                    "groups": groups,
                }
            )
            if group_count >= MAX_COST_GROUPS and len(raw_periods) > len(
                sanitized_periods
            ):
                clipped = True
                break

        issue = (
            AdapterIssue(
                "cost_explorer_invalid_rows",
                "Some Cost Explorer results were omitted because they were invalid.",
            )
            if malformed_count
            else None
        )
        status: Literal["ok", "partial", "error"] = (
            "partial"
            if malformed_count and sanitized_periods
            else "error"
            if malformed_count
            else "ok"
        )
        issues = (issue,) if issue is not None else ()
        return AwsAdapterResult(
            data={
                "region": COST_EXPLORER_REGION,
                "read_only": True,
                "time_period": {
                    "start": normalized.start_date,
                    "end": normalized.end_date,
                },
                "granularity": normalized.granularity,
                "group_by": normalized.group_by,
                "metric": COST_EXPLORER_METRIC,
                "currency": "USD",
                "max_cost_usd": COST_EXPLORER_MAX_COST_USD,
                "monthly_request_limit": MONTHLY_COST_REQUEST_LIMIT,
                "monthly_max_api_cost_usd": MONTHLY_MAX_API_COST_USD,
                "returned_periods": len(sanitized_periods),
                "returned_groups": group_count,
                "truncated": clipped,
                "results_by_time": sanitized_periods,
            },
            sdk_requests=1,
            resources=group_count,
            status=status,
            issues=issues,
        )


def _safe_date(period: object, key: str) -> str | None:
    if not isinstance(period, Mapping):
        return None
    value = period.get(key)
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == value else None


def _safe_amount(metric: object) -> str | None:
    if not isinstance(metric, Mapping):
        return None
    amount = metric.get("Amount")
    if not isinstance(amount, str) or len(amount) > MAX_AMOUNT_CHARS:
        return None
    if metric.get("Unit") != "USD":
        return None
    try:
        decimal_amount = Decimal(amount)
    except InvalidOperation:
        return None
    if not decimal_amount.is_finite():
        return None
    normalized = format(decimal_amount, "f")
    return normalized if len(normalized) <= MAX_AMOUNT_CHARS else None


def _sanitize_group(group: object, group_by: str) -> dict[str, JsonValue] | None:
    if not isinstance(group, Mapping):
        return None
    keys = group.get("Keys")
    if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
        return None
    original_key = keys[0]
    if re.search(r"(?<!\d)\d{12}(?!\d)", original_key):
        return None
    key = _SAFE_DIMENSION_VALUE.sub("_", original_key)[:MAX_DIMENSION_VALUE_CHARS]
    if not key:
        return None
    metrics = group.get("Metrics")
    amount = _safe_amount(
        metrics.get(COST_EXPLORER_METRIC) if isinstance(metrics, Mapping) else None
    )
    if amount is None:
        return None
    return {"key": key, "amount": amount, "unit": "USD"}


def _failure(code: str, message: str, *, sdk_requests: int) -> AwsAdapterResult:
    return AwsAdapterResult(
        data={
            "region": COST_EXPLORER_REGION,
            "read_only": True,
            "metric": COST_EXPLORER_METRIC,
            "currency": "USD",
            "max_cost_usd": COST_EXPLORER_MAX_COST_USD,
            "monthly_request_limit": MONTHLY_COST_REQUEST_LIMIT,
            "monthly_max_api_cost_usd": MONTHLY_MAX_API_COST_USD,
            "returned_periods": 0,
            "returned_groups": 0,
            "truncated": False,
            "results_by_time": [],
        },
        sdk_requests=sdk_requests,
        resources=0,
        status="error",
        issues=(AdapterIssue(code, message),),
    )
