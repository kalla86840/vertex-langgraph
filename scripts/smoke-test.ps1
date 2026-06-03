param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$ErrorActionPreference = "Stop"

$healthUrl = "$($BaseUrl.TrimEnd('/'))/health"
$response = Invoke-RestMethod -Method Get -Uri $healthUrl

if ($response.status -ne "ok") {
    throw "Health check failed for $healthUrl"
}

$response

