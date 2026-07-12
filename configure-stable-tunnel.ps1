$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$envFile = Join-Path $backend ".env"
$envExample = Join-Path $backend ".env.example"

Write-Host "Cloudflare stable Tunnel setup"
Write-Host "Create a remotely-managed Tunnel first."
Write-Host "Set its Public Hostname service to: http://api:8000"
$url = (Read-Host "Stable public URL, for example https://api.example.com").Trim().TrimEnd('/')
if ($url -notmatch '^https://[A-Za-z0-9.-]+$') { throw "A stable https:// hostname is required" }
$secure = Read-Host "Tunnel token (hidden)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ([string]::IsNullOrWhiteSpace($token)) { throw "Tunnel token cannot be empty" }

$values = [ordered]@{ TUNNEL_TOKEN = $token; PUBLIC_BASE_URL = $url }

$lines = [Collections.Generic.List[string]]::new()
$sourceFile = $null
if ((Test-Path -LiteralPath $envFile) -and ((Get-Item -LiteralPath $envFile).Length -gt 0)) {
    $sourceFile = $envFile
} elseif (Test-Path -LiteralPath $envExample) {
    $sourceFile = $envExample
}
if ($null -ne $sourceFile) {
    foreach ($line in @(Get-Content -LiteralPath $sourceFile)) {
        [void]$lines.Add([string]$line)
    }
}

foreach ($entry in $values.GetEnumerator()) {
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($entry.Key))=") {
            $lines[$i] = "$($entry.Key)=$($entry.Value)"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        [void]$lines.Add("$($entry.Key)=$($entry.Value)")
    }
}

[IO.File]::WriteAllLines($envFile, $lines, [Text.UTF8Encoding]::new($false))
Write-Host "Saved. start-public-tunnel.cmd will now keep using $url."
& (Join-Path $PSScriptRoot "start-public-tunnel.ps1")