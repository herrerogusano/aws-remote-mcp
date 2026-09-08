"""Confirmation binding and lifecycle tests."""

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest

from aws_remote_mcp.core.confirmation import (
    ConfirmationError,
    ConfirmationGuard,
    DynamoDbConfirmationGuard,
)
from aws_remote_mcp.core.models import CallerContext


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 28, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class ConditionalFailure(Exception):
    response: ClassVar[dict[str, Any]] = {
        "Error": {"Code": "ConditionalCheckFailedException"}
    }


class FakeDynamoDbClient:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def put_item(self, **request: Any) -> None:
        self.calls.append(("put_item", request))
        digest = request["Item"]["token_digest"]["S"]
        if digest in self.items:
            raise ConditionalFailure
        self.items[digest] = request["Item"]

    def update_item(self, **request: Any) -> None:
        self.calls.append(("update_item", request))
        digest = request["Key"]["token_digest"]["S"]
        item = self.items.get(digest)
        values = request["ExpressionAttributeValues"]
        valid = (
            item is not None
            and item["consumed"]["BOOL"] is False
            and int(item["expires_at"]["N"]) > int(values[":now"]["N"])
            and item["caller_fingerprint"] == values[":caller"]
            and item["action"] == values[":action"]
            and item["payload_digest"] == values[":payload"]
        )
        if not valid:
            raise ConditionalFailure
        assert item is not None
        item["consumed"] = {"BOOL": True}

    def get_item(self, **request: Any) -> dict[str, Any]:
        self.calls.append(("get_item", request))
        digest = request["Key"]["token_digest"]["S"]
        item = self.items.get(digest)
        return {"Item": item} if item is not None else {}


@pytest.fixture
def caller() -> CallerContext:
    return CallerContext("https://issuer.example", "caller-1")


def test_confirmation_is_single_use(caller: CallerContext) -> None:
    guard = ConfirmationGuard()
    payload = {"message": "hello"}
    prepared = guard.prepare(caller, "telegram.send_message", payload)

    guard.consume(prepared.token, caller, "telegram.send_message", payload)

    with pytest.raises(ConfirmationError, match="already") as captured:
        guard.consume(prepared.token, caller, "telegram.send_message", payload)
    assert captured.value.code == "confirmation_replayed"


def test_confirmation_expires(caller: CallerContext) -> None:
    clock = MutableClock()
    guard = ConfirmationGuard(ttl=timedelta(seconds=30), clock=clock)
    prepared = guard.prepare(caller, "telegram.send_message", {"message": "hello"})
    clock.now += timedelta(seconds=30)

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(
            prepared.token, caller, "telegram.send_message", {"message": "hello"}
        )
    assert captured.value.code == "confirmation_expired"


def test_confirmation_rejects_different_caller(caller: CallerContext) -> None:
    guard = ConfirmationGuard()
    payload = {"message": "hello"}
    prepared = guard.prepare(caller, "telegram.send_message", payload)
    other = CallerContext(caller.issuer, "caller-2")

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(prepared.token, other, "telegram.send_message", payload)
    assert captured.value.code == "confirmation_caller_mismatch"


def test_confirmation_rejects_payload_mutation(caller: CallerContext) -> None:
    guard = ConfirmationGuard()
    prepared = guard.prepare(caller, "telegram.send_message", {"message": "approved"})

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(
            prepared.token,
            caller,
            "telegram.send_message",
            {"message": "changed"},
        )
    assert captured.value.code == "confirmation_payload_mismatch"


def test_confirmation_rejects_action_mutation(caller: CallerContext) -> None:
    guard = ConfirmationGuard()
    payload = {"message": "approved"}
    prepared = guard.prepare(caller, "telegram.send_message", payload)

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(prepared.token, caller, "trello.create_card", payload)
    assert captured.value.code == "confirmation_action_mismatch"


def test_dynamodb_confirmation_survives_guard_recreation(
    caller: CallerContext,
) -> None:
    client = FakeDynamoDbClient()
    first = DynamoDbConfirmationGuard(table_name="confirmations", client=client)
    prepared = first.prepare(caller, "telegram.send_message", {"message": "hello"})

    second = DynamoDbConfirmationGuard(table_name="confirmations", client=client)
    second.consume(
        prepared.token, caller, "telegram.send_message", {"message": "hello"}
    )

    assert [name for name, _ in client.calls] == ["put_item", "update_item"]
    stored = next(iter(client.items.values()))
    assert stored["consumed"] == {"BOOL": True}
    assert prepared.token not in str(stored)


def test_dynamodb_confirmation_replay_is_rejected_atomically(
    caller: CallerContext,
) -> None:
    client = FakeDynamoDbClient()
    guard = DynamoDbConfirmationGuard(table_name="confirmations", client=client)
    payload = {"message": "hello"}
    prepared = guard.prepare(caller, "telegram.send_message", payload)
    guard.consume(prepared.token, caller, "telegram.send_message", payload)

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(prepared.token, caller, "telegram.send_message", payload)

    assert captured.value.code == "confirmation_replayed"
    assert [name for name, _ in client.calls] == [
        "put_item",
        "update_item",
        "update_item",
        "get_item",
    ]


def test_dynamodb_confirmation_mismatch_does_not_consume(
    caller: CallerContext,
) -> None:
    client = FakeDynamoDbClient()
    guard = DynamoDbConfirmationGuard(table_name="confirmations", client=client)
    prepared = guard.prepare(caller, "telegram.send_message", {"message": "approved"})

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(
            prepared.token,
            caller,
            "telegram.send_message",
            {"message": "changed"},
        )

    assert captured.value.code == "confirmation_payload_mismatch"
    assert next(iter(client.items.values()))["consumed"] == {"BOOL": False}


def test_dynamodb_confirmation_expiry_is_checked_before_ttl_cleanup(
    caller: CallerContext,
) -> None:
    clock = MutableClock()
    client = FakeDynamoDbClient()
    guard = DynamoDbConfirmationGuard(
        table_name="confirmations",
        client=client,
        ttl=timedelta(seconds=30),
        clock=clock,
    )
    payload = {"message": "hello"}
    prepared = guard.prepare(caller, "telegram.send_message", payload)
    clock.now += timedelta(seconds=30)

    with pytest.raises(ConfirmationError) as captured:
        guard.consume(prepared.token, caller, "telegram.send_message", payload)

    assert captured.value.code == "confirmation_expired"
