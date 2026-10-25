# Start the project's Mosquitto broker in the foreground (Ctrl+C to stop).
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts\start_broker.ps1 -Mode plain|tls|mtls
param(
    [ValidateSet("plain", "tls", "mtls")]
    [string]$Mode = "plain"
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root   # config files use paths relative to the project root

$mosqDir = if ($env:MOSQUITTO_DIR) { $env:MOSQUITTO_DIR } else { "C:\Program Files\mosquitto" }
$exe = Join-Path $mosqDir "mosquitto.exe"
$conf = "config\broker_$Mode.conf"
$ports = @{ plain = 1884; tls = 8883; mtls = 8884 }

if (-not (Test-Path $exe)) { Write-Error "mosquitto.exe not found at $exe"; exit 1 }
if (-not (Test-Path "config\secrets\passwd")) {
    Write-Error "Password file missing. Run (in backend\): ..\.venv\Scripts\python scripts\setup_credentials.py"; exit 1
}
if ($Mode -ne "plain" -and -not (Test-Path "certificates\server\server.crt")) {
    Write-Error "Server certificate missing. Run: powershell -ExecutionPolicy Bypass -File scripts\gen_certs.ps1"; exit 1
}
$busy = Get-NetTCPConnection -State Listen -LocalPort $ports[$Mode] -ErrorAction SilentlyContinue
if ($busy) { Write-Error "Port $($ports[$Mode]) already in use by PID $($busy[0].OwningProcess)."; exit 1 }

New-Item -ItemType Directory -Force logs | Out-Null
Write-Host "Starting Mosquitto ($Mode) on 127.0.0.1:$($ports[$Mode]) using $conf" -ForegroundColor Cyan
& $exe -c $conf
