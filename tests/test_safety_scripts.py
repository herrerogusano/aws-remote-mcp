"""Static regressions for the externally bounded DEV validation window."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
OPEN_SCRIPT = ROOT / "scripts" / "open-dev-window.ps1"
CLOSE_SCRIPT = ROOT / "scripts" / "close-dev-window.ps1"


def test_open_window_installs_guards_before_enabling_endpoint() -> None:
    script = OPEN_SCRIPT.read_text(encoding="utf-8")

    schedule = script.index('"scheduler", "create-schedule"')
    alarm = script.index('"cloudwatch", "put-metric-alarm"')
    concurrency = script.index('"lambda", "put-function-concurrency"')
    endpoint = script.index('"apigatewayv2", "update-api"')

    assert schedule < alarm < concurrency < endpoint
    assert "[ValidateRange(1, 5)]" in script
    assert "$RequestThreshold = 20" in script
    assert '"--action-after-completion", "DELETE"' in script
    assert "Input='{}'" in script
    assert "ConvertTo-Json" not in script
    assert '"--no-disable-execute-api-endpoint"' in script
    assert '"ce", "get-cost-and-usage"' not in script


def test_open_window_has_fail_closed_cleanup() -> None:
    script = OPEN_SCRIPT.read_text(encoding="utf-8")

    catch_block = script[script.index("catch {") :]
    assert "--disable-execute-api-endpoint --region" in catch_block
    assert "--reserved-concurrent-executions 0" in catch_block
    assert "cloudwatch delete-alarms" in catch_block
    assert "scheduler delete-schedule" in catch_block


def test_manual_close_disables_endpoint_before_stopping_compute() -> None:
    script = CLOSE_SCRIPT.read_text(encoding="utf-8")

    endpoint = script.index("--disable-execute-api-endpoint --region")
    concurrency = script.index("--reserved-concurrent-executions 0")
    alarm = script.index("cloudwatch delete-alarms")

    assert endpoint < concurrency < alarm
    assert "scheduler list-schedules" in script
    assert "scheduler delete-schedule" in script
