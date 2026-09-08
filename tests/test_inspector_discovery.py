"""Execute the PowerShell recovery logic offline with synthetic attempts."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("scenario", "expected_retries", "expected_success"),
    [
        ("success", 0, True),
        ("recover", 1, True),
        ("other_error", 0, False),
        ("invalid_json", 0, False),
        ("expired", 0, False),
        ("wrong_audience", 0, False),
        ("wrong_issuer", 0, False),
        ("wrong_scope", 0, False),
        ("wrong_client", 0, False),
        ("id_token", 0, False),
        ("late", 0, False),
        ("retry_failure", 1, False),
    ],
)
def test_discovery_recovery(
    scenario: str, expected_retries: int, expected_success: bool
) -> None:
    shell = shutil.which("pwsh")
    assert shell, "PowerShell is required for executable recovery tests"
    script = r"""
$ErrorActionPreference = 'Stop'
. ./scripts/inspector-discovery.ps1
$scenario = '__SCENARIO__'
$script:retries = 0
$script:initials = 0
$success = $false
try {
    $result = Invoke-BoundedInspectorDiscovery -InitialAttempt {
        $script:initials++
        if ($scenario -eq 'success') {
            return [pscustomobject]@{ ExitCode=0; Output='listing' }
        }
        $message = 'StreamableHTTPClientTransport already started! ' +
            'If using Client class, note that connect() calls start() automatically.'
        if ($scenario -eq 'other_error') { $message = 'HTTP 401' }
        $output = @{error=@{message=$message}} | ConvertTo-Json -Compress
        if ($scenario -eq 'invalid_json') { $output = 'invalid' }
        [pscustomobject]@{ ExitCode=1; Output=$output }
    } -StoredAttempt {
        $script:retries++
        $code = if ($scenario -eq 'retry_failure') { 1 } else { 0 }
        [pscustomobject]@{ ExitCode=$code; Output='listing' }
    } -ReadContract {
        [pscustomobject]@{
            IssuerMatches=($scenario -ne 'wrong_issuer')
            AudienceMatches=($scenario -ne 'wrong_audience')
            ScopeMatches=($scenario -ne 'wrong_scope')
            ClientMatches=($scenario -ne 'wrong_client')
            TokenUse=$(if ($scenario -eq 'id_token') { 'id' } else { 'access' })
            IsUnexpired=($scenario -ne 'expired')
        }
    } -CanRetry { $scenario -ne 'late' } -WarningAction SilentlyContinue
    $success = $result -eq 'listing'
} catch { $success = $false }
if ($script:initials -ne 1) { throw 'Initial call count mismatch' }
if ($script:retries -ne __RETRIES__) { throw 'Retry count mismatch' }
if ($success -ne $__SUCCESS__) { throw 'Outcome mismatch' }
"""
    script = (
        script.replace("__SCENARIO__", scenario)
        .replace("__RETRIES__", str(expected_retries))
        .replace("__SUCCESS__", str(expected_success).lower())
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
