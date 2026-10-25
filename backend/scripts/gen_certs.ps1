# Generate the LOCAL DEMO PKI: ECC P-256 keys + ECDSA-SHA256 certificates.
#   * Root CA         certificates\ca\ca.{key,crt}
#   * Broker          certificates\server\server.{key,crt}   (SAN: localhost, 127.0.0.1, ::1)
#   * Clients         certificates\clients\<name>.{key,crt}  (gateway, collector, benchmark, dev-001..)
#   * Negative tests  certificates\negative\*               (via scripts\gen_negative_certs.py)
#
# These certificates are for a local college demonstration ONLY. They are not
# publicly trusted and must never be used in production.
#
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts\gen_certs.ps1 [-Devices 20] [-Force]
param(
    [int]$Devices = 20,
    [switch]$Force
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$openssl = if ($env:OPENSSL_BIN) { $env:OPENSSL_BIN } else { "C:\Program Files\Git\usr\bin\openssl.exe" }
if (-not (Test-Path $openssl)) { Write-Error "OpenSSL not found at $openssl (set OPENSSL_BIN)"; exit 1 }
$cnf = "config/openssl.cnf"

if ((Test-Path "certificates\ca\ca.crt") -and -not $Force) {
    Write-Host "Certificates already exist. Use -Force to regenerate (this invalidates all old certs)." -ForegroundColor Yellow
    exit 0
}
foreach ($d in "ca", "server", "clients", "negative") {
    if (Test-Path "certificates\$d") { Remove-Item -Recurse -Force "certificates\$d" }
    New-Item -ItemType Directory -Force "certificates\$d" | Out-Null
}

function Invoke-OpenSSL {
    # Run openssl and judge success by EXIT CODE. (OpenSSL prints informational
    # messages such as "self-signature ok" on stderr, which Windows PowerShell 5.1
    # would otherwise turn into terminating errors.)
    $ErrorActionPreference = "Continue"
    $out = & $openssl @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        $out | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        throw "openssl $($args[0]) failed (exit $LASTEXITCODE)"
    }
}

function New-EcKey($path) {
    # NIST P-256 (a.k.a. prime256v1 / secp256r1), PKCS#8 PEM
    Invoke-OpenSSL genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out $path
}

function New-SignedCert($name, $subject, $dir, $extSection, $days) {
    $key = "certificates/$dir/$name.key"; $csr = "certificates/$dir/$name.csr"; $crt = "certificates/$dir/$name.crt"
    New-EcKey $key
    Invoke-OpenSSL req -config $cnf -new -key $key -subj $subject -out $csr
    # No -CAserial: OpenSSL 3 assigns a random 159-bit serial number
    Invoke-OpenSSL x509 -req -in $csr -CA certificates/ca/ca.crt -CAkey certificates/ca/ca.key `
        -sha256 -days $days -extfile $cnf -extensions $extSection -out $crt
    Remove-Item $csr
}

Write-Host "OpenSSL: $(& $openssl version)" -ForegroundColor Cyan

# 1. Root CA (self-signed, 825 days)
Write-Host "[1/4] Root CA (ECDSA P-256)"
New-EcKey "certificates/ca/ca.key"
Invoke-OpenSSL req -config $cnf -x509 -new -key certificates/ca/ca.key -sha256 -days 825 `
    -subj "/C=IN/O=IoT Secure Gateway (DEMO)/CN=IoT-Demo-Local-CA" -extensions v3_ca -out certificates/ca/ca.crt

# 2. Broker server certificate (397 days = max lifetime browsers accept for TLS server certs)
Write-Host "[2/4] Broker certificate (CN=localhost, SAN=localhost,127.0.0.1,::1)"
New-SignedCert "server" "/C=IN/O=IoT Secure Gateway (DEMO)/CN=localhost" "server" "v3_server" 397

# 3. Client certificates - CN becomes the MQTT username in mTLS mode
$clients = @("gateway", "collector", "benchmark") + (1..$Devices | ForEach-Object { "dev-{0:D3}" -f $_ })
Write-Host "[3/4] $($clients.Count) client certificates ($($clients[0]) .. $($clients[-1]))"
foreach ($c in $clients) { New-SignedCert $c "/C=IN/O=IoT Secure Gateway (DEMO)/CN=$c" "clients" "v3_client" 397 }

# 4. Deliberately BAD certificates for the security tests
Write-Host "[4/4] Negative-test certificates"
$rootVenv = Join-Path (Split-Path -Parent $root) ".venv\Scripts\python.exe"   # venv lives at the project root
$py = if (Test-Path $rootVenv) { $rootVenv } else { "python" }
& $py scripts\gen_negative_certs.py
if ($LASTEXITCODE -ne 0) { throw "gen_negative_certs.py failed" }

# Restrict private keys to the current user (removes inherited ACLs)
Get-ChildItem certificates -Recurse -Filter *.key | ForEach-Object {
    icacls $_.FullName /inheritance:r /grant:r "${env:USERNAME}:(R,W)" | Out-Null
}

# Self-check: every leaf must verify against the CA
& $openssl verify -CAfile certificates/ca/ca.crt certificates/server/server.crt certificates/clients/gateway.crt | Write-Host
Write-Host "`nDone. Private keys (*.key) are git-ignored and readable only by $env:USERNAME." -ForegroundColor Green
Write-Host "Inspect a certificate:  & '$openssl' x509 -in certificates/server/server.crt -noout -text"
