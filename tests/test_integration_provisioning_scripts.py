"""Static safety regressions for interactive integration provisioning."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
PROVISION = ROOT / "scripts" / "provision-integration-config.ps1"
CAPTURE = ROOT / "scripts" / "save-integration-credentials.ps1"
TEMPLATE = ROOT / "template.yaml"
RUNTIME = ROOT / "src" / "aws_remote_mcp" / "adapters" / "external_integrations.py"

PARAMETER_PATH = "/portfolio/aws-remote-mcp/dev/integrations"


def test_ssm_parameter_uses_non_reserved_namespace_everywhere() -> None:
    provision = PROVISION.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert PARAMETER_PATH in provision
    assert f"Default: {PARAMETER_PATH}" in template
    assert 'startswith("/portfolio/aws-remote-mcp/dev/")' in runtime
    assert "Default: /aws-remote-mcp/" not in template


def test_aws_preflight_runs_before_any_secret_prompt() -> None:
    script = PROVISION.read_text(encoding="utf-8")

    preflight = script.index("aws ssm describe-parameters")
    cache_or_prompt = script.index("if (Test-Path -LiteralPath $CredentialCachePath")
    put_parameter = script.index("aws ssm put-parameter")

    assert preflight < cache_or_prompt < put_parameter
    assert "aws ssm get-parameter" not in script


def test_trello_list_url_delimits_the_interpolated_identifier() -> None:
    script = PROVISION.read_text(encoding="utf-8")

    assert "[Parameter(Mandatory)][string]$TrelloListId" in script
    assert "/1/lists/${TrelloListId}?fields=name,closed" in script
    assert "/1/lists/$TrelloListId?" not in script


def test_dpapi_handoff_is_bounded_and_deleted_only_after_creation() -> None:
    capture = CAPTURE.read_text(encoding="utf-8")
    provision = PROVISION.read_text(encoding="utf-8")

    assert capture.count("ConvertFrom-SecureString") == 3
    assert "SetAccessRuleProtection($true, $false)" in capture
    assert 'Join-Path $env:LOCALAPPDATA "aws-remote-mcp' in capture
    assert "$parameterCreated = $true" in provision
    cleanup = provision.index("$parameterCreated -and")
    removal = provision.index("Remove-Item -LiteralPath $resolvedCachePath", cleanup)
    assert removal > cleanup


def test_plaintext_credentials_are_not_cli_arguments() -> None:
    script = PROVISION.read_text(encoding="utf-8")

    assert '--value "file://$resolvedTemporaryPath"' in script
    assert "--value $configuration" not in script
    assert "--with-decryption" not in script
