[CmdletBinding()]
param(
    [string]$Region = "eu-west-1",
    [string]$ParameterName = "/portfolio/aws-remote-mcp/dev/integrations",
    [Parameter(Mandatory)][string]$TrelloListId,
    [string]$CredentialCachePath = (
        Join-Path $env:LOCALAPPDATA "aws-remote-mcp\integration-credentials.json"
    )
)

$ErrorActionPreference = "Stop"
$temporaryPath = $null
$telegramToken = $null
$trelloKey = $null
$trelloToken = $null
$credentialCacheUsed = $false
$parameterCreated = $false

function Read-ProtectedText([string]$Prompt) {
    $protected = Read-Host $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($protected)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $protected.Dispose()
    }
}

function Unprotect-Text([string]$EncryptedValue) {
    $protected = ConvertTo-SecureString $EncryptedValue
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($protected)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $protected.Dispose()
    }
}

function Invoke-TrelloRead {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][hashtable]$Headers,
        [Parameter(Mandatory)][string]$Stage
    )

    try {
        Invoke-RestMethod -Uri $Uri -Headers $Headers -Method Get
    }
    catch {
        $statusCode = "unknown"
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [string][int]$_.Exception.Response.StatusCode
        }
        $safeMessage = [string]$_.ErrorDetails.Message
        if (-not $safeMessage) {
            $safeMessage = [string]$_.Exception.Message
        }
        $safeMessage = ($safeMessage -replace "[\r\n]+", " ").Trim()
        if ($safeMessage.Length -gt 300) {
            $safeMessage = $safeMessage.Substring(0, 300)
        }
        throw "Trello $Stage failed (HTTP $statusCode): $safeMessage"
    }
}

try {
    $existingParameterCount = aws ssm describe-parameters `
        --parameter-filters "Key=Name,Option=Equals,Values=$ParameterName" `
        --region $Region `
        --query "length(Parameters)" `
        --output text
    if ($LASTEXITCODE -ne 0) {
        throw "AWS preflight could not inspect Parameter Store."
    }
    if ([int]$existingParameterCount -ne 0) {
        throw "The integration parameter already exists; refusing to overwrite it."
    }

    if (Test-Path -LiteralPath $CredentialCachePath -PathType Leaf) {
        $cacheRoot = [IO.Path]::GetFullPath(
            (Join-Path $env:LOCALAPPDATA "aws-remote-mcp")
        )
        $resolvedCachePath = (Resolve-Path -LiteralPath $CredentialCachePath).Path
        if (-not $resolvedCachePath.StartsWith(
            "$cacheRoot\",
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "Credential cache is outside the expected local directory."
        }
        $cache = Get-Content -Raw -LiteralPath $resolvedCachePath | ConvertFrom-Json
        $telegramToken = Unprotect-Text $cache.telegram_bot_token
        $trelloKey = Unprotect-Text $cache.trello_api_key
        $trelloToken = Unprotect-Text $cache.trello_api_token
        $credentialCacheUsed = $true
    }
    else {
        $trelloKey = Read-ProtectedText "Trello API key"
        $trelloToken = Read-ProtectedText "Trello permanent API token"
    }

    if (
        $trelloKey -notmatch "^[A-Za-z0-9_-]{8,256}$" -or
        $trelloToken -notmatch "^[A-Za-z0-9_-]{8,256}$"
    ) {
        throw "The Trello credentials have an unexpected format."
    }
    if ($TrelloListId -notmatch "^[A-Za-z0-9]+$") {
        throw "The Trello list identifier has an unexpected format."
    }

    $trelloHeaders = @{
        Authorization = 'OAuth oauth_consumer_key="{0}", oauth_token="{1}"' -f `
            $trelloKey, $trelloToken
    }
    $trelloMember = Invoke-TrelloRead `
        -Uri "https://api.trello.com/1/members/me?fields=id" `
        -Headers $trelloHeaders `
        -Stage "credential validation"
    if (-not $trelloMember.id) {
        throw "Trello credential validation returned an invalid response."
    }

    $trelloList = Invoke-TrelloRead `
        -Uri "https://api.trello.com/1/lists/${TrelloListId}?fields=name,closed" `
        -Headers $trelloHeaders `
        -Stage "list validation"
    if ($trelloList.name -cne "MCP Inbox" -or $trelloList.closed -ne $false) {
        throw "The Trello destination is not the expected open MCP Inbox list."
    }

    if (-not $credentialCacheUsed) {
        $telegramToken = Read-ProtectedText "Telegram bot token"
    }
    if ($telegramToken -notmatch "^[0-9]{5,20}:[A-Za-z0-9_-]{20,128}$") {
        throw "The Telegram token has an unexpected format."
    }
    try {
        $telegram = Invoke-RestMethod `
            -Uri "https://api.telegram.org/bot$telegramToken/getUpdates" `
            -Method Get
    }
    catch {
        throw "Telegram rejected the credential or could not be reached."
    }
    $chatIds = @(
        $telegram.result |
            ForEach-Object { $_.message.chat } |
            Where-Object type -EQ "private" |
            ForEach-Object { [string]$_.id } |
            Sort-Object -Unique
    )
    if ($chatIds.Count -ne 1 -or $chatIds[0] -notmatch "^-?[0-9]{1,20}$") {
        throw "Expected exactly one private Telegram chat. Send /start to the bot and retry."
    }

    $configuration = @{
        telegram = @{
            bot_token = $telegramToken
            destinations = @{ owner = $chatIds[0] }
        }
        trello = @{
            api_key = $trelloKey
            api_token = $trelloToken
            destinations = @(
                @{
                    board = "portfolio"
                    list = "inbox"
                    list_id = $TrelloListId
                }
            )
        }
    } | ConvertTo-Json -Depth 6 -Compress

    $temporaryPath = [IO.Path]::GetTempFileName()
    $resolvedTemporaryPath = (Resolve-Path -LiteralPath $temporaryPath).Path
    $resolvedTempRoot = (Resolve-Path -LiteralPath ([IO.Path]::GetTempPath())).Path
    if (-not $resolvedTemporaryPath.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to use a temporary file outside the user temp directory."
    }

    $acl = Get-Acl -LiteralPath $resolvedTemporaryPath
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
    Set-Acl -LiteralPath $resolvedTemporaryPath -AclObject $acl
    [IO.File]::WriteAllText($resolvedTemporaryPath, $configuration)

    aws ssm put-parameter `
        --name $ParameterName `
        --description "DEV Telegram and Trello integration configuration" `
        --type SecureString `
        --tier Standard `
        --value "file://$resolvedTemporaryPath" `
        --region $Region `
        --tags Key=environment,Value=dev Key=project,Value=aws-remote-mcp `
        --query "{Version:Version,Tier:Tier}" `
        --output json
    if ($LASTEXITCODE -ne 0) {
        throw "AWS did not create the integration parameter."
    }
    $parameterCreated = $true

    aws ssm describe-parameters `
        --parameter-filters "Key=Name,Option=Equals,Values=$ParameterName" `
        --region $Region `
        --query "Parameters[0].{Name:Name,Type:Type,Tier:Tier}" `
        --output json
    if ($LASTEXITCODE -ne 0) {
        throw "AWS created the parameter, but metadata verification failed."
    }
}
finally {
    $telegramToken = $null
    $trelloKey = $null
    $trelloToken = $null
    $configuration = $null
    if ($temporaryPath -and (Test-Path -LiteralPath $temporaryPath -PathType Leaf)) {
        [IO.File]::WriteAllText($temporaryPath, "")
        Remove-Item -LiteralPath $temporaryPath -Force
    }
    if (
        $parameterCreated -and
        $credentialCacheUsed -and
        (Test-Path -LiteralPath $resolvedCachePath -PathType Leaf)
    ) {
        [IO.File]::WriteAllText($resolvedCachePath, "")
        Remove-Item -LiteralPath $resolvedCachePath -Force
    }
}
