"""Monthly Cost Explorer quota is atomic, persistent and fail closed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from aws_remote_mcp.core.cost_quota import (
    CostQuotaError,
    DynamoDbCostRequestLimiter,
    InMemoryCostRequestLimiter,
)


@dataclass
class MutableClock:
    now: datetime = datetime(2026, 9, 16, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class ConditionalFailure(Exception):
    response: ClassVar[dict[str, dict[str, str]]] = {
        "Error": {"Code": "ConditionalCheckFailedException"}
    }


class FakeQuotaDynamoDbClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.counts: dict[str, int] = {}
        self.calls: list[dict[str, Any]] = []

    def update_item(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("private provider failure")
        key = kwargs["Key"]["token_digest"]["S"]
        limit = int(kwargs["ExpressionAttributeValues"][":limit"]["N"])
        count = self.counts.get(key, 0)
        if count >= limit:
            raise ConditionalFailure
        self.counts[key] = count + 1


def test_in_memory_quota_resets_only_at_next_utc_month() -> None:
    clock = MutableClock()
    limiter = InMemoryCostRequestLimiter(limit=3, clock=clock)

    for _ in range(3):
        limiter.acquire()
    with pytest.raises(CostQuotaError) as exhausted:
        limiter.acquire()
    assert exhausted.value.code == "cost_monthly_limit_exceeded"

    clock.now = datetime(2026, 10, 1, tzinfo=UTC)
    limiter.acquire()


def test_dynamodb_quota_atomically_rejects_the_fourth_monthly_slot() -> None:
    client = FakeQuotaDynamoDbClient()
    limiter = DynamoDbCostRequestLimiter(
        table_name="confirmations",
        client=client,
        clock=MutableClock(),
    )

    for _ in range(3):
        limiter.acquire()
    with pytest.raises(CostQuotaError) as exhausted:
        limiter.acquire()

    assert exhausted.value.code == "cost_monthly_limit_exceeded"
    assert len(client.calls) == 4
    assert len(client.counts) == 1
    request = client.calls[0]
    assert request["ConditionExpression"] == (
        "attribute_not_exists(#count) OR #count < :limit"
    )
    assert request["ExpressionAttributeValues"][":limit"] == {"N": "3"}
    assert request["ExpressionAttributeValues"][":expires"] == {
        "N": str(int(datetime(2026, 10, 1, tzinfo=UTC).timestamp()))
    }
    assert "aws.cost_explorer" not in str(request["Key"])


def test_dynamodb_quota_uses_a_new_key_next_month() -> None:
    clock = MutableClock()
    client = FakeQuotaDynamoDbClient()
    limiter = DynamoDbCostRequestLimiter(
        table_name="confirmations",
        client=client,
        clock=clock,
    )

    limiter.acquire()
    september_key = next(iter(client.counts))
    clock.now = datetime(2026, 10, 1, tzinfo=UTC)
    limiter.acquire()

    assert len(client.counts) == 2
    october_key = next(key for key in client.counts if key != september_key)
    assert october_key != september_key


def test_dynamodb_quota_sanitizes_provider_failure() -> None:
    limiter = DynamoDbCostRequestLimiter(
        table_name="confirmations",
        client=FakeQuotaDynamoDbClient(fail=True),
    )

    with pytest.raises(CostQuotaError) as unavailable:
        limiter.acquire()

    assert unavailable.value.code == "cost_quota_unavailable"
    assert "private provider failure" not in str(unavailable.value)
