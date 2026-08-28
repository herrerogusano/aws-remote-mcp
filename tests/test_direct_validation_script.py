"""Static regressions for direct, API-closed Lambda validation."""

from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "validate-direct-lambda.ps1"


def test_direct_validation_is_bounded_and_fail_closed() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    schedule = script.index('"scheduler", "create-schedule"')
    enable = script.index('"lambda", "delete-function-concurrency"')
    invoke = script.index("$listed = Invoke-DirectMcp")
    cleanup = script.index("finally {", script.index("$validation ="))

    assert schedule < enable < invoke < cleanup
    assert script.count("Invoke-DirectMcp") == 4
    assert "--no-disable-execute-api-endpoint" not in script
    assert "Direct validation requires the API endpoint to remain disabled." in script
    assert "--reserved-concurrent-executions 0" in script[cleanup:]
    assert "--disable-execute-api-endpoint --region" in script[cleanup:]
    assert "scheduler delete-schedule" in script[cleanup:]
    assert '"ce", "get-cost-and-usage"' not in script
