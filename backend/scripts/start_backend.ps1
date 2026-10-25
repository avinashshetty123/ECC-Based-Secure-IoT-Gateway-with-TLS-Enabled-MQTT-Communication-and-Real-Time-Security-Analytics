# Start the backend API (broker control, wire tap, gateway, collector, analytics) on http://127.0.0.1:8600.
# The web UI is the Next.js app in ..\frontend (npm run dev -> http://localhost:3000).
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1
$backend = Split-Path -Parent $PSScriptRoot
Set-Location $backend
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"   # venv lives at the project root
if (-not (Test-Path $py)) {
    Write-Error "Python venv not found. From the project root run: python -m venv .venv; .venv\Scripts\python -m pip install -r backend\requirements.txt"; exit 1
}
if (-not (Test-Path "config\secrets\credentials.json")) {
    Write-Host "First run: generating per-device passwords..." -ForegroundColor Cyan
    & $py scripts\setup_credentials.py
}
if (-not (Test-Path "certificates\server\server.crt")) {
    Write-Host "First run: generating the demo ECC certificates..." -ForegroundColor Cyan
    & powershell -ExecutionPolicy Bypass -File scripts\gen_certs.ps1
}
& $py -m app.visualizer @args
