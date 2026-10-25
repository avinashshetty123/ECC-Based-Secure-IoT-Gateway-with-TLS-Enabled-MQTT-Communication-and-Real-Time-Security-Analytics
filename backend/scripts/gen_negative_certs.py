"""Generate deliberately INVALID certificates for the security test suite.

Every file here is expected to be REJECTED somewhere:
  rogue_ca.crt / rogue_client.{crt,key}  CN=dev-001 but signed by an UNTRUSTED CA  -> broker rejects (mTLS)
  expired_client.{crt,key}               CN=dev-001, real CA, expired in 2021       -> broker rejects (mTLS)
  wronghost_server.{crt,key}             real CA, SAN=wrong.example only           -> client rejects (hostname)
  server_as_client.{crt,key}             real CA, EKU=serverAuth only (CN=dev-001) -> observed in tests

Called by scripts/gen_certs.ps1 after the real CA exists.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parent.parent
CERTS = ROOT / "certificates"
OUT = CERTS / "negative"
ORG = "IoT Secure Gateway (DEMO)"


def _name(cn: str, org: str = ORG) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, org), x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _save(stem: str, key: ec.EllipticCurvePrivateKey | None, cert: x509.Certificate) -> None:
    (OUT / f"{stem}.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    if key is not None:
        (OUT / f"{stem}.key").write_bytes(
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        )


def _leaf(cn, issuer_name, issuer_key, eku, not_before, not_after, san=None):
    key = ec.generate_private_key(ec.SECP256R1())
    b = (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
    )
    if san:
        b = b.add_extension(x509.SubjectAlternativeName(san), critical=False)
    return key, b.sign(issuer_key, hashes.SHA256())


def main() -> int:
    ca_crt_path, ca_key_path = CERTS / "ca" / "ca.crt", CERTS / "ca" / "ca.key"
    if not ca_crt_path.exists():
        print("Real CA missing - run scripts\\gen_certs.ps1", file=sys.stderr)
        return 1
    ca_cert = x509.load_pem_x509_certificate(ca_crt_path.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
    OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)

    # 1. Rogue CA + a client claiming to be dev-001
    rogue_key = ec.generate_private_key(ec.SECP256R1())
    rogue_name = _name("Rogue-Attacker-CA", "Not Our Organisation")
    rogue_ca = (
        x509.CertificateBuilder()
        .subject_name(rogue_name)
        .issuer_name(rogue_name)
        .public_key(rogue_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(rogue_key, hashes.SHA256())
    )
    _save("rogue_ca", None, rogue_ca)
    _save("rogue_client", *_leaf("dev-001", rogue_name, rogue_key, ExtendedKeyUsageOID.CLIENT_AUTH,
                                 now - dt.timedelta(days=1), now + dt.timedelta(days=365)))

    # 2. Expired client certificate signed by the REAL CA
    _save("expired_client", *_leaf("dev-001", ca_cert.subject, ca_key, ExtendedKeyUsageOID.CLIENT_AUTH,
                                   dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
                                   dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)))

    # 3. Server cert from the REAL CA but for the WRONG hostname
    _save("wronghost_server", *_leaf("wrong.example", ca_cert.subject, ca_key, ExtendedKeyUsageOID.SERVER_AUTH,
                                     now - dt.timedelta(days=1), now + dt.timedelta(days=365),
                                     san=[x509.DNSName("wrong.example")]))

    # 4. Real CA, right CN, but issued for the wrong PURPOSE (server, not client)
    _save("server_as_client", *_leaf("dev-001", ca_cert.subject, ca_key, ExtendedKeyUsageOID.SERVER_AUTH,
                                     now - dt.timedelta(days=1), now + dt.timedelta(days=365),
                                     san=[x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]))

    print(f"Negative-test certificates written to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
