"""Atomic monthly request quota for billable Cost Explorer calls."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from aws_remote_mcp.core.cost_query import COST_EXPLORER_OPERATION

MONTHLY_COST_REQUEST_LIMIT = 3
MONTHLY_MAX_API_COST_USD = "0.03"


class CostQuotaError(RuntimeError):
    """Sanitized failure to acquire a monthly Cost Explorer request slot."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class CostRequestLimiter(Protocol):
    def acquire(self) -> None: ...


class InMemoryCostRequestLimiter:
    """Process-local quota implementation for local development and tests."""

    def __init__(
        self,
        *,
        limit: int = MONTHLY_COST_REQUEST_LIMIT,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("Cost request limit must be positive.")
        self._limit = limit
        self._clock = clock or (lambda: datetime.now(UTC))
        self._period: str | None = None
        self._count = 0

    def acquire(self) -> None:
        now = _aware_now(self._clock)
        period = _period(now)
        if period != self._period:
            self._period = period
            self._count = 0
        if self._count >= self._limit:
            raise CostQuotaError(
                "cost_monthly_limit_exceeded",
                "The monthly Cost Explorer request limit has been reached.",
            )
        self._count += 1


class DynamoDbCostRequestLimiter:
    """Atomically acquire one monthly quota slot in the confirmation table."""

    def __init__(
        self,
        *,
        table_name: str,
        client: Any,
        action: str = COST_EXPLORER_OPERATION,
        limit: int = MONTHLY_COST_REQUEST_LIMIT,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not table_name:
            raise ValueError("Cost quota table name is required.")
        if not action or limit <= 0:
            raise ValueError("Cost quota configuration is invalid.")
        self._table_name = table_name
        self._client = client
        self._action = action
        self._limit = limit
        self._clock = clock or (lambda: datetime.now(UTC))

    def acquire(self) -> None:
        now = _aware_now(self._clock)
        period = _period(now)
        key_digest = hashlib.sha256(f"{self._action}:{period}".encode()).hexdigest()
        expires_epoch = int(_next_period(now).timestamp())
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"token_digest": {"S": key_digest}},
                UpdateExpression=(
                    "SET #count = if_not_exists(#count, :zero) + :one, "
                    "expires_at = :expires"
                ),
                ConditionExpression=("attribute_not_exists(#count) OR #count < :limit"),
                ExpressionAttributeNames={"#count": "count"},
                ExpressionAttributeValues={
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                    ":limit": {"N": str(self._limit)},
                    ":expires": {"N": str(expires_epoch)},
                },
            )
        except Exception as error:
            if _is_conditional_failure(error):
                raise CostQuotaError(
                    "cost_monthly_limit_exceeded",
                    "The monthly Cost Explorer request limit has been reached.",
                ) from error
            raise CostQuotaError(
                "cost_quota_unavailable",
                "The Cost Explorer monthly quota is unavailable.",
            ) from error


def _aware_now(clock: Callable[[], datetime]) -> datetime:
    value = clock()
    if value.tzinfo is None:
        raise ValueError("Cost quota clock must return a timezone-aware datetime.")
    return value.astimezone(UTC)


def _period(value: datetime) -> str:
    return value.strftime("%Y-%m")


def _next_period(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=UTC)
    return datetime(value.year, value.month + 1, 1, tzinfo=UTC)


def _is_conditional_failure(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    details = response.get("Error")
    return isinstance(details, dict) and details.get("Code") == (
        "ConditionalCheckFailedException"
    )
