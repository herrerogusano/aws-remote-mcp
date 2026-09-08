[CmdletBinding()]
param(
    [string]$BoardName = "AWS Remote MCP",
    [string]$ListName = "MCP Inbox",
    [string]$BoardId
)

$ErrorActionPreference = "Stop"

function ConvertFrom-ProtectedInput {
    param([Security.SecureString]$Value)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

$protectedKey = Read-Host "Trello API key" -AsSecureString
$protectedToken = Read-Host "Trello API token" -AsSecureString
$apiKey = $null
$apiToken = $null

try {
    $apiKey = ConvertFrom-ProtectedInput $protectedKey
    $apiToken = ConvertFrom-ProtectedInput $protectedToken

    if ($apiKey -notmatch "^[A-Za-z0-9]+$" -or $apiToken -notmatch "^[A-Za-z0-9]+$") {
        throw "The Trello credentials have an unexpected format."
    }

    $headers = @{
        Authorization = 'OAuth oauth_consumer_key="{0}", oauth_token="{1}"' -f `
            $apiKey, $apiToken
    }
    if ($BoardId) {
        $resolvedBoardId = $BoardId
    }
    else {
        $boardResponse = Invoke-RestMethod `
                -Uri "https://api.trello.com/1/members/me/boards?fields=name&filter=open" `
                -Headers $headers `
                -Method Get
        $boards = @($boardResponse)
        $matchingBoards = @($boards | Where-Object name -CEQ $BoardName)
        if ($matchingBoards.Count -ne 1) {
            $availableBoards = ($boards | ForEach-Object name) -join ", "
            throw "Expected exactly one open board named '$BoardName'; found $($matchingBoards.Count). Available: $availableBoards"
        }
        $resolvedBoardId = $matchingBoards[0].id
    }

    if ($resolvedBoardId -notmatch "^[A-Za-z0-9]+$") {
        throw "Trello returned an unexpected board identifier."
    }

    $listResponse = Invoke-RestMethod `
            -Uri "https://api.trello.com/1/boards/$resolvedBoardId/lists?fields=name&filter=open" `
            -Headers $headers `
            -Method Get
    $lists = @($listResponse)
    $matchingLists = @($lists | Where-Object name -CEQ $ListName)
    if ($matchingLists.Count -ne 1) {
        $availableLists = ($lists | ForEach-Object name) -join ", "
        throw "Expected exactly one open list named '$ListName'; found $($matchingLists.Count). Available: $availableLists"
    }

    Write-Output $matchingLists[0].id
}
finally {
    $apiKey = $null
    $apiToken = $null
    $protectedKey.Dispose()
    $protectedToken.Dispose()
}
