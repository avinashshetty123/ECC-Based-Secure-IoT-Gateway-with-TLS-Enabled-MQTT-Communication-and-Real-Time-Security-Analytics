# Run Experiments A (plain), B (TLS), C (mTLS) and save raw + aggregated results to backend\reports\benchmarks\.
# Usage:
#   powershell -ExecutionPolicy Bypass -File backend\scripts\run_benchmarks.ps1            # full run (~8 min)
#   powershell -ExecutionPolicy Bypass -File backend\scripts\run_benchmarks.ps1 --quick    # ~1.5 min smoke test
# Stop the backend's live session first (it uses the same broker ports).
# For fair numbers: plug in the charger and close heavy apps.
$backend = Split-Path -Parent $PSScriptRoot
Set-Location $backend
$py = Join-Path (Split-Path -Parent $backend) ".venv\Scripts\python.exe"
& $py -m app.analytics.benchmark @args
exit $LASTEXITCODE
