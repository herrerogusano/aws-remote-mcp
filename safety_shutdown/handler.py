"""Idempotently close the temporary DEV endpoint and remove its traffic alarm."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Callable
from typing import Any, Protocol, cast


class ApiGatewayClient(Protocol):
    def update_api(self, *, ApiId: str, DisableExecuteApiEndpoint: bool) -> object: ...


class LambdaClient(Protocol):
    def put_function_concurrency(
        self, *, FunctionName: str, ReservedConcurrentExecutions: int
    ) -> object: ...


class CloudWatchClient(Protocol):
    def delete_alarms(self, *, AlarmNames: list[str]) -> object: ...


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def close_test_window(
    api_client: ApiGatewayClient,
    lambda_client: LambdaClient,
    cloudwatch_client: CloudWatchClient,
    *,
    api_id: str,
    function_name: str,
    alarm_name: str,
) -> None:
    """Attempt every fail-closed action even if an earlier action fails."""

    actions: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "disable_api",
            lambda: api_client.update_api(ApiId=api_id, DisableExecuteApiEndpoint=True),
        ),
        (
            "stop_lambda",
            lambda: lambda_client.put_function_concurrency(
                FunctionName=function_name, ReservedConcurrentExecutions=0
            ),
        ),
        (
            "delete_traffic_alarm",
            lambda: cloudwatch_client.delete_alarms(AlarmNames=[alarm_name]),
        ),
    )
    failures: list[str] = []
    for action_name, action in actions:
        try:
            action()
        except Exception:
            failures.append(action_name)

    print(
        json.dumps(
            {
                "event": "dev_test_window_closed",
                "apiDisabled": "disable_api" not in failures,
                "lambdaStopped": "stop_lambda" not in failures,
                "alarmDeleted": "delete_traffic_alarm" not in failures,
                "failedActions": failures,
            },
            separators=(",", ":"),
        )
    )
    if failures:
        raise RuntimeError("One or more fail-closed actions did not complete.")


def handler(event: dict[str, Any], context: Any) -> dict[str, bool]:
    """Lambda entry point used by both Scheduler and the traffic alarm topic."""

    del event, context
    boto3 = importlib.import_module("boto3")
    close_test_window(
        cast("ApiGatewayClient", boto3.client("apigatewayv2")),
        cast("LambdaClient", boto3.client("lambda")),
        cast("CloudWatchClient", boto3.client("cloudwatch")),
        api_id=required_environment("TARGET_API_ID"),
        function_name=required_environment("TARGET_FUNCTION_NAME"),
        alarm_name=required_environment("TRAFFIC_ALARM_NAME"),
    )
    return {"closed": True}
