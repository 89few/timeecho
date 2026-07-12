$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "backend")
docker compose up --build -d
docker compose ps
Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "User web: http://127.0.0.1:8000/app"
Write-Host "Admin:    http://127.0.0.1:8000/admin"
