function Invoke-BoundedInspectorDiscovery {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][scriptblock]$InitialAttempt,
        [Parameter(Mandatory)][scriptblock]$StoredAttempt,
        [Parameter(Mandatory)][scriptblock]$ReadContract,
        [Parameter(Mandatory)][scriptblock]$CanRetry
    )

    $attempt = & $InitialAttempt
    if ($attempt.ExitCode -eq 0) { return $attempt.Output }

    $expectedError = 'StreamableHTTPClientTransport already started! If using Client class, note that connect() calls start() automatically.'
    try { $document = ($attempt.Output -join "`n") | ConvertFrom-Json }
    catch { throw 'Inspector discovery failed without a recognized recovery condition' }
    if ($document.error.message -cne $expectedError) {
        throw 'Inspector discovery failed without a recognized recovery condition'
    }
    $contract = & $ReadContract
    if (
        $contract.IssuerMatches -ne $true -or
        $contract.AudienceMatches -ne $true -or
        $contract.ScopeMatches -ne $true -or
        $contract.ClientMatches -ne $true -or
        $contract.TokenUse -cne 'access' -or
        $contract.IsUnexpired -ne $true -or
        -not (& $CanRetry)
    ) { throw 'Inspector discovery recovery refused by token or time checks' }

    Write-Warning 'Restarting tool discovery once with stored authorization after the known transport lifecycle error'
    $attempt = & $StoredAttempt
    if ($attempt.ExitCode -ne 0) { throw 'Inspector stored-authorization discovery failed' }
    return $attempt.Output
}
