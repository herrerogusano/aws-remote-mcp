"""AWS operation policy tests."""

import pytest

from aws_remote_mcp.core.operations import (
    OperationBlockedError,
    OperationClassification,
    build_default_registry,
)


def test_unknown_operation_fails_closed() -> None:
    registry = build_default_registry()

    with pytest.raises(OperationBlockedError) as captured:
        registry.require_automatic("aws.unknown.list_everything")

    assert captured.value.classification is OperationClassification.UNKNOWN


@pytest.mark.parametrize(
    "operation",
    [
        "aws.cost_explorer.get_cost_and_usage",
        "telegram.send_message",
        "trello.create_card",
        "secrets.read_value",
    ],
)
def test_only_verified_free_reads_run_automatically(operation: str) -> None:
    with pytest.raises(OperationBlockedError):
        build_default_registry().require_automatic(operation)


def test_verified_free_read_is_allowed() -> None:
    spec = build_default_registry().require_automatic("aws.sts.get_caller_identity")

    assert spec.classification is OperationClassification.FREE_VERIFIED_READ
