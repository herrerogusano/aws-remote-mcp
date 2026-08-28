"""Confirmation binding and lifecycle tests."""

from datetime import UTC, datetime, timedelta

import pytest

from aws_remote_mcp.core.confirmation import ConfirmationError, ConfirmationGuard
from aws_remote_mcp.core.models import CallerContext


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 28, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


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
