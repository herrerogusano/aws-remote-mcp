"""Offline application service tests through fake adapters."""

import pytest

from aws_remote_mcp.adapters.fakes import (
    FakeAwsAdapter,
    FakeTelegramAdapter,
    FakeTrelloAdapter,
)
from aws_remote_mcp.adapters.protocols import AdapterError
from aws_remote_mcp.core.confirmation import ConfirmationGuard
from aws_remote_mcp.core.models import (
    CallerContext,
    OperationCounters,
    WriteLimitExceededError,
)
from aws_remote_mcp.core.operations import build_default_registry
from aws_remote_mcp.services.tools import ToolService


@pytest.fixture
def caller() -> CallerContext:
    return CallerContext("https://issuer.example", "caller-1")


@pytest.fixture
def adapters() -> tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter]:
    return FakeAwsAdapter(), FakeTelegramAdapter(), FakeTrelloAdapter()


def build_service(
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
    *,
    max_result_bytes: int = 65_536,
) -> ToolService:
    aws, telegram, trello = adapters
    return ToolService(
        operations=build_default_registry(),
        confirmations=ConfirmationGuard(),
        aws=aws,
        telegram=telegram,
        trello=trello,
        telegram_destinations=frozenset({"test-chat"}),
        trello_destinations=frozenset({("test-board", "test-list")}),
        max_result_bytes=max_result_bytes,
    )


def test_safe_aws_operation_uses_fake_adapter(
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    aws, _, _ = adapters
    aws.responses["aws.sts.get_caller_identity"] = {"principal": "fake"}

    result = build_service(adapters).run_aws_operation(
        "aws.sts.get_caller_identity", {}
    )

    assert result.status == "ok"
    assert result.data == {"principal": "fake"}
    assert result.counters.sdk_requests == 1


def test_unknown_aws_operation_never_reaches_adapter(
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    result = build_service(adapters).run_aws_operation("aws.unknown", {})

    assert result.status == "error"
    assert result.errors[0].code == "operation_blocked"
    assert adapters[0].calls == []


def test_oversized_result_is_replaced_with_bounded_error(
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    adapters[0].responses["aws.sts.get_caller_identity"] = {"value": "x" * 100}

    result = build_service(adapters, max_result_bytes=32).run_aws_operation(
        "aws.sts.get_caller_identity", {}
    )

    assert result.status == "error"
    assert result.data == {}
    assert result.errors[0].code == "result_too_large"


def test_telegram_requires_exact_confirmation_and_writes_once(
    caller: CallerContext,
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    service = build_service(adapters)
    preview = service.prepare_telegram_message(caller, "test-chat", "hello")
    assert preview.confirmation is not None

    result = service.execute_telegram_message(
        caller, preview.confirmation.token, "test-chat", "hello"
    )
    replay = service.execute_telegram_message(
        caller, preview.confirmation.token, "test-chat", "hello"
    )

    assert result.status == "ok"
    assert result.counters.external_writes_attempted == 1
    assert result.counters.external_writes_succeeded == 1
    assert replay.errors[0].code == "confirmation_replayed"
    assert adapters[1].calls == [("test-chat", "hello")]


def test_trello_destination_is_allowlisted(
    caller: CallerContext,
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    result = build_service(adapters).prepare_trello_card(
        caller, "other-board", "other-list", "title", "description"
    )

    assert result.status == "error"
    assert result.errors[0].code == "destination_not_allowed"


def test_ambiguous_write_failure_consumes_confirmation(
    caller: CallerContext,
    adapters: tuple[FakeAwsAdapter, FakeTelegramAdapter, FakeTrelloAdapter],
) -> None:
    adapters[1].failure = AdapterError(
        "telegram_timeout", "Telegram outcome is unknown.", retryable=False
    )
    service = build_service(adapters)
    preview = service.prepare_telegram_message(caller, "test-chat", "hello")
    assert preview.confirmation is not None

    failed = service.execute_telegram_message(
        caller, preview.confirmation.token, "test-chat", "hello"
    )
    replay = service.execute_telegram_message(
        caller, preview.confirmation.token, "test-chat", "hello"
    )

    assert failed.errors[0].code == "telegram_timeout"
    assert failed.counters.external_writes_attempted == 1
    assert failed.counters.external_writes_succeeded == 0
    assert replay.errors[0].code == "confirmation_replayed"
    assert len(adapters[1].calls) == 1


def test_counter_rejects_second_write() -> None:
    counters = OperationCounters()
    counters.record_external_write_attempt()

    with pytest.raises(WriteLimitExceededError):
        counters.record_external_write_attempt()
