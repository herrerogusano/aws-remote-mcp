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
    assert script.count("Invoke-DirectMcp") == 11
    assert "if ($ValidateExternalWrites)" in script
    assert "if ($ValidateCostExplorer)" in script
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
    assert script.count('name = "preparar_consulta_costes_aws"') == 1
    assert script.count('name = "consultar_costes_aws"') == 1
    assert '$costPreview.data.preview.max_cost_usd -ne "0.01"' in script
    assert "$costPreview.data.preview.monthly_request_limit -ne 3" in script
    assert "$costResult.counters.sdk_requests -ne 1" in script
    assert "$costResult.data.returned_groups -gt 100" in script
    assert 'name = "listar_inventario_aws"' in script
    assert "$inventoryContent.counters.sdk_requests -ne 2" in script
    assert "$inventoryContent.counters.resources -gt 20" in script
    assert "$inventoryContent.counters.external_writes_attempted -ne 0" in script
    assert 'name = "buscar_recursos_aws"' in script
    assert "$expectedToolNames | Sort-Object" in script
    assert "[ValidateRange(1, 5)][int]$ResourceLimit = 5" in script
    assert "query = $ResourceQuery" in script
    assert "limit = $ResourceLimit" in script
    assert "$resourceSearchContent.data.returned -gt $ResourceLimit" in script
    assert "if ($IncludeResourceDetails)" in script
    assert '$validation["resource_explorer_resources"]' in script
    assert "$resourceSearchContent.counters.sdk_requests -ne 1" in script
    assert "$resourceSearchContent.counters.external_writes_attempted -ne 0" in script
    assert '@("ok", "partial") -notcontains $resourceSearchContent.status' in script
    assert '$resourceSearchContent.status -eq "ok" -and' in script
    assert "$resourceSearchWarningCodes.Count -ne 0" in script
    assert '$resourceSearchContent.status -eq "partial" -and' in script
    assert "$resourceSearchWarningCodes.Count -eq 0" in script
    assert '$_ -ne "resource_explorer_invalid_resources"' in script
    assert "message = $TelegramMessage" in script
    assert "title = $TrelloTitle" in script
    assert "description = $TrelloDescription" in script
