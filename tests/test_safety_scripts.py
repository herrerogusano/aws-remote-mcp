"""Static regressions for the externally bounded DEV validation window."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
OPEN_SCRIPT = ROOT / "scripts" / "open-dev-window.ps1"
CLOSE_SCRIPT = ROOT / "scripts" / "close-dev-window.ps1"
TOTP_SCRIPT = ROOT / "scripts" / "enroll-cognito-totp.ps1"
DIRECT_SCRIPT = ROOT / "scripts" / "validate-direct-lambda.ps1"
INSPECTOR_SCRIPT = ROOT / "scripts" / "validate-inspector-window.ps1"


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
    assert 'Get-StackOutput "DevStageName"' in script
    assert '"Name=Stage,Value=$stageName"' in script
    assert 'Authentication    = "Cognito JWT with aws-remote-mcp/use"' in script
    assert 'AuthorizationType -ne "JWT"' in script
    assert 'AuthorizationScopes[0] -ne "aws-remote-mcp/use"' in script
    assert "SOFTWARE_TOKEN_MFA" in script
    assert "TotpEnrollmentGate" in script
    assert "JwtConfiguration.Issuer -ne $issuer" in script
    assert "JwtConfiguration.Audience[0] -ne $endpoint" in script
    assert "ThrottlingRateLimit -ne 1" in script
    assert "Refusing to overlap or overwrite an existing validation window" in script
    assert "The bounded window did not reach its exact open state" in script
    assert "[switch]$UseUnreservedConcurrency" in script
    assert '"lambda", "delete-function-concurrency"' in script
    assert '"--quota-code", "L-B99A9384"' in script
    assert "$quota.Quota.Value -ne 10" in script
    assert '"lambda", "get-account-settings"' in script
    assert "$accountSettings.AccountLimit.ConcurrentExecutions -ne 10" in script
    assert (
        "$accountSettings.AccountLimit.UnreservedConcurrentExecutions -ne 10" in script
    )
    assert "$RequestThreshold -gt 15" in script
    assert "unreserved-account-cap-10" in script
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


def test_totp_enrollment_gate_is_fail_closed() -> None:
    script = TOTP_SCRIPT.read_text(encoding="utf-8")

    assert 'Deploy-EnrollmentGate "true"' in script
    finally_block = script[script.index("finally {") :]
    assert 'Deploy-EnrollmentGate "false"' in finally_block
    assert "aws-remote-mcp/use" in finally_block
    assert "aws.cognito.signin.user.admin" not in finally_block
    assert "http://127.0.0.1:6276/oauth/callback" in script
    assert "DisableExecuteApiEndpoint" in script
    assert "ReservedConcurrentExecutions -ne 0" in script
    assert '"ce", "get-cost-and-usage"' not in script


def test_direct_validation_matches_default_stage_gateway_contract() -> None:
    script = DIRECT_SCRIPT.read_text(encoding="utf-8")

    assert 'rawPath          = "/mcp"' in script
    assert 'path      = "/mcp"' in script
    assert "stage       = '$default'" in script
    assert "/dev/mcp" not in script


def test_inspector_validation_is_pinned_bounded_and_fail_closed() -> None:
    script = INSPECTOR_SCRIPT.read_text(encoding="utf-8")

    prepare = script.index("--cli --help")
    open_window = script.index("& $openScript -WindowMinutes 5")
    inspector = script.index("--method tools/list")
    finally_block = script[script.index("finally {") :]

    assert prepare < open_window < inspector
    assert "@modelcontextprotocol/inspector@2.4.0" in script
    assert "-RequestThreshold 15" in script
    assert "-UseUnreservedConcurrency" in script
    assert "function Get-RedactedJwtContract" in script
    assert "IssuerMatches" in script
    assert "AudienceMatches" in script
    assert "ScopeMatches" in script
    assert "ClientMatches" in script
    assert "Redacted OAuth JWT contract" in script
    assert "access_token" not in script.split("return [pscustomobject]@{", 1)[1]
    assert "SOFTWARE_TOKEN_MFA" in script
    assert 'AuthorizationType -ne "JWT"' in script
    assert 'AuthorizationScopes[0] -ne "aws-remote-mcp/use"' in script
    assert "The API has unexpected routes" in script
    assert "JwtConfiguration.Issuer -ne $issuer" in script
    assert "JwtConfiguration.Audience[0] -ne $endpoint" in script
    assert "ThrottlingRateLimit -ne 1" in script
    assert "Temporary validation controls from an earlier window still exist" in script
    assert "--offline --yes" in script
    assert "--stored-auth-only" in script
    assert "& $closeScript" in finally_block
    assert "Remove-Item -LiteralPath $resolvedStorage -Recurse -Force" in finally_block
    assert '"ce", "get-cost-and-usage"' not in script
