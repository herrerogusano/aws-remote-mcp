"""Tests for the fail-closed DEV window kill switch."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from safety_shutdown.handler import close_test_window, required_environment


@dataclass
class FakeApiClient:
    calls: list[tuple[str, bool]] = field(default_factory=list)
    fails: bool = False

    def update_api(self, *, ApiId: str, DisableExecuteApiEndpoint: bool) -> object:
        self.calls.append((ApiId, DisableExecuteApiEndpoint))
        if self.fails:
            raise RuntimeError("synthetic API failure")
        return {}


@dataclass
class FakeLambdaClient:
    calls: list[tuple[str, int]] = field(default_factory=list)
    fails: bool = False

    def put_function_concurrency(
        self, *, FunctionName: str, ReservedConcurrentExecutions: int
    ) -> object:
        self.calls.append((FunctionName, ReservedConcurrentExecutions))
        if self.fails:
            raise RuntimeError("synthetic Lambda failure")
        return {}


@dataclass
class FakeCloudWatchClient:
    calls: list[list[str]] = field(default_factory=list)
    fails: bool = False

    def delete_alarms(self, *, AlarmNames: list[str]) -> object:
        self.calls.append(AlarmNames)
        if self.fails:
            raise RuntimeError("synthetic CloudWatch failure")
        return {}


def test_close_window_disables_api_stops_lambda_and_removes_alarm() -> None:
    api = FakeApiClient()
    function = FakeLambdaClient()
    cloudwatch = FakeCloudWatchClient()

    close_test_window(
        api,
        function,
        cloudwatch,
        api_id="api-id",
        function_name="function-name",
        alarm_name="alarm-name",
    )

    assert api.calls == [("api-id", True)]
    assert function.calls == [("function-name", 0)]
    assert cloudwatch.calls == [["alarm-name"]]


def test_close_window_attempts_every_action_before_reporting_failure() -> None:
    api = FakeApiClient(fails=True)
    function = FakeLambdaClient(fails=True)
    cloudwatch = FakeCloudWatchClient()

    with pytest.raises(RuntimeError, match="fail-closed"):
        close_test_window(
            api,
            function,
            cloudwatch,
            api_id="api-id",
            function_name="function-name",
            alarm_name="alarm-name",
        )

    assert api.calls == [("api-id", True)]
    assert function.calls == [("function-name", 0)]
    assert cloudwatch.calls == [["alarm-name"]]


def test_required_environment_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TARGET_API_ID", raising=False)

    with pytest.raises(RuntimeError, match="TARGET_API_ID"):
        required_environment("TARGET_API_ID")
