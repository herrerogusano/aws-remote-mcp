[CmdletBinding()]
param(
    [string]$CredentialCachePath = (
        Join-Path $env:LOCALAPPDATA "aws-remote-mcp\integration-credentials.json"
    )
)

$ErrorActionPreference = "Stop"
$cacheRoot = Join-Path $env:LOCALAPPDATA "aws-remote-mcp"
$resolvedCacheRoot = [IO.Path]::GetFullPath($cacheRoot)
$resolvedCachePath = [IO.Path]::GetFullPath($CredentialCachePath)
if (-not $resolvedCachePath.StartsWith(
    "$resolvedCacheRoot\",
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "Credential cache must remain inside the local aws-remote-mcp directory."
}

New-Item -ItemType Directory -Path $resolvedCacheRoot -Force | Out-Null
if (Test-Path -LiteralPath $resolvedCachePath) {
    throw "The encrypted credential cache already exists; refusing to overwrite it."
}

$telegram = Read-Host "Telegram bot token" -AsSecureString
$trelloKey = Read-Host "Trello API key" -AsSecureString
$trelloToken = Read-Host "Trello permanent API token" -AsSecureString

try {
    $encrypted = @{
        telegram_bot_token = ConvertFrom-SecureString $telegram
        trello_api_key = ConvertFrom-SecureString $trelloKey
        trello_api_token = ConvertFrom-SecureString $trelloToken
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($resolvedCachePath, $encrypted)

    $acl = Get-Acl -LiteralPath $resolvedCachePath
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($accessRule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleAll($accessRule)
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $rule = [Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $resolvedCachePath -AclObject $acl

    Write-Output "Credentials encrypted for the current Windows user."
    Write-Output "Cache: $resolvedCachePath"
}
finally {
    $encrypted = $null
    $telegram.Dispose()
    $trelloKey.Dispose()
    $trelloToken.Dispose()
}
