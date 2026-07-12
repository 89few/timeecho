$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "backend")
$compose = @('compose','-f','docker-compose.yml','-f','docker-compose.prod.yml')
& docker @compose up -d
$envFile = Join-Path (Get-Location) ".env"
$config = @{}
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^([^#=]+)=(.*)$') { $config[$matches[1].Trim()] = $matches[2].Trim() }
    }
}

if ($config['TUNNEL_TOKEN'] -and $config['PUBLIC_BASE_URL']) {
    & docker @compose --profile tunnel up -d tunnel
    $url = $config['PUBLIC_BASE_URL'].TrimEnd('/')
    Write-Host "Waiting for stable tunnel: $url"
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $health = & curl.exe -fsS --max-time 5 "$url/health" 2>$null
        if ($LASTEXITCODE -eq 0) {
            [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'current-public-url.txt'), $url, [Text.UTF8Encoding]::new($false))
            Write-Host "Stable public backend: $url"
            exit 0
        }
        Start-Sleep -Seconds 2
    }
    throw "Stable tunnel started but health check failed. Check Cloudflare public hostname -> http://api:8000."
}

& docker @compose --profile tunnel-quick up -d tunnel-quick
Write-Host "Waiting for a temporary public HTTPS address..."
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    $logs = & docker @compose logs --no-color tunnel-quick 2>&1
    $match = [regex]::Match(($logs -join "`n"), 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($match.Success) {
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'current-public-url.txt'), $match.Value, [Text.UTF8Encoding]::new($false))
        Write-Host ""
        Write-Host "Public backend: $($match.Value)"
        Write-Warning "This is a temporary address and can change after restart. Run configure-stable-tunnel.cmd for one-time permanent setup."
        exit 0
    }
    Start-Sleep -Seconds 2
}
throw "Tunnel started but no public URL was found. Run: docker compose logs tunnel-quick"
