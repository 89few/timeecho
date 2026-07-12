$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$envFile = Join-Path $backend ".env"
$envExample = Join-Path $backend ".env.example"

Write-Host "TimeEcho official email sender setup"
Write-Host "1. QQ Mail (authorization code required)"
Write-Host "2. 163 Mail (client authorization password required)"
Write-Host "3. Gmail (app password required)"
Write-Host "4. Outlook / Microsoft 365"
Write-Host "5. Custom SMTP"
$provider = Read-Host "Select 1-5"
$email = (Read-Host "Official sender email address").Trim()
if ($email -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw "Invalid email address" }

$hostName = ""
$port = 587
$tls = "true"
$ssl = "false"
switch ($provider) {
    "1" { $hostName = "smtp.qq.com"; $port = 465; $tls = "false"; $ssl = "true" }
    "2" { $hostName = "smtp.163.com"; $port = 465; $tls = "false"; $ssl = "true" }
    "3" { $hostName = "smtp.gmail.com"; $port = 587; $tls = "true"; $ssl = "false" }
    "4" { $hostName = "smtp.office365.com"; $port = 587; $tls = "true"; $ssl = "false" }
    "5" {
        $hostName = (Read-Host "SMTP host").Trim()
        $port = [int](Read-Host "SMTP port")
        $ssl = if ((Read-Host "Use implicit SSL? y/N") -match '^[yY]') { "true" } else { "false" }
        $tls = if ($ssl -eq "true") { "false" } elseif ((Read-Host "Use STARTTLS? Y/n") -match '^[nN]') { "false" } else { "true" }
    }
    default { throw "Invalid provider selection" }
}

$secure = Read-Host "App password / authorization code (hidden)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ([string]::IsNullOrWhiteSpace($password)) { throw "Authorization code cannot be empty" }

$values = [ordered]@{
    EMAIL_VERIFICATION_REQUIRED = "true"
    EMAIL_ALLOW_UNVERIFIED_REGISTRATION = "false"
    EMAIL_DEV_CODE_ENABLED = "false"
    SMTP_HOST = $hostName
    SMTP_PORT = "$port"
    SMTP_USERNAME = $email
    SMTP_PASSWORD = $password
    SMTP_FROM_EMAIL = $email
    SMTP_FROM_NAME = "TimeEcho"
    SMTP_USE_TLS = $tls
    SMTP_USE_SSL = $ssl
}

# Always create a real mutable List. An existing but empty .env makes Get-Content
# return $null, which caused the original script to fail on $lines.Add(...).
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

Set-Location $backend
docker compose up --build -d
Write-Host ""
Write-Host "SMTP settings saved. The backend now requires real email verification."
$test = Read-Host "Send a real test verification code to $email now? Y/n"
if ($test -notmatch '^[nN]') {
    $body = @{ email = $email; purpose = "register" } | ConvertTo-Json
    $result = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/auth/email/send-code" -ContentType "application/json" -Body $body
    Write-Host $result.message
}