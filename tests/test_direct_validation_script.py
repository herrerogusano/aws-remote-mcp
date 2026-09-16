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
    assert script.count("Invoke-DirectMcp") == 9
    assert "if ($ValidateExternalWrites)" in script
    assert script.count('name = "preparar_mensaje_telegram"') == 1
    assert script.count('name = "enviar_mensaje_telegram"') == 1
    assert script.count('name = "preparar_tarjeta_trello"') == 1
    assert script.count('name = "crear_tarjeta_trello"') == 1
    assert "--no-disable-execute-api-endpoint" not in script
    assert "Direct validation requires the API endpoint to remain disabled." in script
    assert "--reserved-concurrent-executions 0" in script[cleanup:]
    assert "--disable-execute-api-endpoint --region" in script[cleanup:]
    assert "scheduler delete-schedule" in script[cleanup:]
    assert '"ce", "get-cost-and-usage"' not in script
    assert 'name = "listar_inventario_aws"' in script
    assert "$inventoryContent.counters.sdk_requests -ne 2" in script
    assert "$inventoryContent.counters.resources -gt 20" in script
    assert "$inventoryContent.counters.external_writes_attempted -ne 0" in script
    assert 'name = "buscar_recursos_aws"' in script
    assert "$expectedToolNames | Sort-Object" in script
    assert 'query = "service:lambda region:eu-west-1"' in script
    assert "$resourceSearchContent.data.returned -gt 5" in script
    assert "$resourceSearchContent.counters.sdk_requests -ne 1" in script
    assert "$resourceSearchContent.counters.external_writes_attempted -ne 0" in script
