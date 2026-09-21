"""Validated, deliberately narrow AWS Cost Explorer query parameters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MAX_COST_QUERY_DAYS = 31
COST_EXPLORER_OPERATION = "aws.cost_explorer.get_cost_and_usage"
COST_EXPLORER_METRIC = "UnblendedCost"
COST_EXPLORER_MAX_COST_USD = "0.01"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_GRANULARITIES = frozenset({"DAILY", "MONTHLY"})
_GROUP_BY_DIMENSIONS = frozenset({"SERVICE", "REGION"})


class CostQueryValidationError(ValueError):
    """A cost query does not fit the product's fixed safe query contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class CostExplorerQuery:
    start_date: str
    end_date: str
    granularity: str
    group_by: str


def validate_cost_explorer_query(
    start_date: object,
    end_date: object,
    granularity: object,
    group_by: object,
) -> CostExplorerQuery:
    """Validate exact ISO dates and the fixed dimensions/metrics contract."""

    parsed_start = _parse_iso_date(start_date, "start_date")
    parsed_end = _parse_iso_date(end_date, "end_date")
    if parsed_end <= parsed_start:
        raise CostQueryValidationError(
            "invalid_cost_period", "Cost query end_date must be after start_date."
        )
    if (parsed_end - parsed_start).days > MAX_COST_QUERY_DAYS:
        raise CostQueryValidationError(
            "cost_period_too_long", "Cost query period cannot exceed 31 days."
        )
    if not isinstance(granularity, str) or granularity not in _GRANULARITIES:
        raise CostQueryValidationError(
            "invalid_cost_granularity",
            "Cost query granularity must be DAILY or MONTHLY.",
        )
    if not isinstance(group_by, str) or group_by not in _GROUP_BY_DIMENSIONS:
        raise CostQueryValidationError(
            "invalid_cost_group_by",
            "Cost query grouping must be SERVICE or REGION.",
        )
    return CostExplorerQuery(
        start_date=parsed_start.isoformat(),
        end_date=parsed_end.isoformat(),
        granularity=granularity,
        group_by=group_by,
    )


def _parse_iso_date(value: object, name: str) -> date:
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        raise CostQueryValidationError(
            "invalid_cost_date", f"Cost query {name} must use YYYY-MM-DD format."
        )
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CostQueryValidationError(
            "invalid_cost_date", f"Cost query {name} is not a valid calendar date."
        ) from error
