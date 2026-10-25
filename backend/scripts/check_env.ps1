# Phase 1 environment check for the ECC + TLS MQTT Gateway project.
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1

$ErrorActionPreference = "Continue"
$script:failures = 0

function Report($name, $ok, $detail) {
    if ($ok) { Write-Host ("[ OK ] {0,-22} {1}" -f $name, $detail) -ForegroundColor Green }
    else     { Write-Host ("[FAIL] {0,-22} {1}" -f $name, $detail) -ForegroundColor Red; $script:failures++ }
}

function Try-Cmd($exe, $args_) {
    try { return (& $exe @args_ 2>&1 | Out-String).Trim() } catch { return $null }
}

Write-Host "`n=== Phase 1: environment check ===`n"

# Python 3.10+ (64-bit)
$py = Try-Cmd "python" @("-c", "import sys,struct;print(sys.version.split()[0], struct.calcsize('P')*8)")
if ($py) {
    $parts = $py.Split(" ")
    $ver = [version]$parts[0]
    Report "Python" (($ver -ge [version]"3.10") -and ($parts[1] -eq "64")) "$($parts[0]) ($($parts[1])-bit)"
} else { Report "Python" $false "not found on PATH" }

# pip
$pip = Try-Cmd "python" @("-m", "pip", "--version")
Report "pip" ($pip -match "^pip") $(if ($pip) { $pip.Split(" ")[1] } else { "not found" })

# venv module
$venv = Try-Cmd "python" @("-c", "import venv;print('ok')")
Report "venv module" ($venv -eq "ok") ""

# Python's linked OpenSSL + TLS 1.3
$pyssl = Try-Cmd "python" @("-c", "import ssl;print(ssl.OPENSSL_VERSION,'| TLS1.3:',ssl.HAS_TLSv1_3)")
Report "Python ssl" ($pyssl -match "TLS1.3: True") $pyssl

# Git
$git = Try-Cmd "git" @("--version")
Report "Git" ($git -match "git version") $git

# OpenSSL CLI: PATH first, then the copy bundled with Git for Windows
$openssl = $null
$cmd = Get-Command openssl -ErrorAction SilentlyContinue
if ($cmd) { $openssl = $cmd.Source }
elseif (Test-Path "C:\Program Files\Git\usr\bin\openssl.exe") { $openssl = "C:\Program Files\Git\usr\bin\openssl.exe" }
if ($openssl) {
    $ov = Try-Cmd $openssl @("version")
    $p256 = (Try-Cmd $openssl @("ecparam", "-list_curves")) -match "prime256v1"
    Report "OpenSSL CLI" ($ov -match "OpenSSL 3") "$ov  [$openssl]"
    Report "ECC P-256 support" $p256 "prime256v1"
} else { Report "OpenSSL CLI" $false "not found (install Git for Windows or add openssl to PATH)" }

# Mosquitto
$mosq = $null
$mcmd = Get-Command mosquitto -ErrorAction SilentlyContinue
if ($mcmd) { $mosq = $mcmd.Source }
elseif (Test-Path "C:\Program Files\mosquitto\mosquitto.exe") { $mosq = "C:\Program Files\mosquitto\mosquitto.exe" }
if ($mosq) {
    $mdir = Split-Path $mosq
    $mv = Try-Cmd $mosq @("-h")
    $mvLine = if ($mv -match "mosquitto version [\d\.]+") { $Matches[0] } else { "version unknown" }
    Report "Mosquitto broker" $true "$mvLine  [$mosq]"
    foreach ($tool in "mosquitto_pub.exe", "mosquitto_sub.exe", "mosquitto_passwd.exe") {
        Report $tool (Test-Path (Join-Path $mdir $tool)) ""
    }
    $onPath = [bool](Get-Command mosquitto_pub -ErrorAction SilentlyContinue)
    Report "Mosquitto on PATH" $onPath $(if ($onPath) { "" } else { "add $mdir to PATH" })
    $svc = Get-Service mosquitto -ErrorAction SilentlyContinue
    if ($svc) { Write-Host ("[INFO] Mosquitto service     status={0} (harmless: it uses 1883, the project uses 1884/8883/8884)" -f $svc.Status) -ForegroundColor Yellow }
} else { Report "Mosquitto broker" $false "not installed" }

# Ports we will use (must be free)
foreach ($port in 1884, 8883, 8884, 8885, 8501) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    Report "Port $port free" (-not $busy) $(if ($busy) { "in use by PID $($busy[0].OwningProcess)" } else { "" })
}

# OneDrive warning (private keys would sync to the cloud; SQLite may lock)
$root = (Get-Location).Path
if ($root -match "OneDrive") {
    Write-Host "[WARN] Project is inside OneDrive: $root" -ForegroundColor Yellow
    Write-Host "       Recommended: move it to C:\dev\iot-secure-gateway (see README)." -ForegroundColor Yellow
}

# Hardware summary
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name
Write-Host "[INFO] CPU: $cpu | RAM: $ram GB"

Write-Host ""
if ($script:failures -eq 0) { Write-Host "All checks passed. Ready for Phase 2." -ForegroundColor Green }
else { Write-Host "$script:failures check(s) failed. Fix them before Phase 3." -ForegroundColor Red }
