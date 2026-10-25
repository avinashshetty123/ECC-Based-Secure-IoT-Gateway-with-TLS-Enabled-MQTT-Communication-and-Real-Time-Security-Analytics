"""Security tests for the TLS (Experiment B) and mTLS (Experiment C) brokers.

Maps to the security-test plan in the project brief:
  1  valid client connects                      -> test_tls_valid_client..., test_mtls_valid_device...
  2  untrusted certificate rejected             -> test_client_rejects_untrusted_broker, test_mtls_rogue_ca_client_rejected
  3  invalid / mismatched identity rejected     -> test_hostname_mismatch_rejected, test_mtls_expired..., test_mtls_wrong_purpose...,
                                                   test_mtls_device_cannot_impersonate_another_device
  4  missing / invalid credentials rejected     -> test_tls_wrong_password_rejected, test_mtls_no_client_cert_rejected
  9  certificate verification stays enabled     -> test_no_insecure_tls_settings_in_source
"""
import json
import re
import ssl

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from app.config import CERT_DIR, ROOT, BrokerEndpoint
from app.mqtt.client_factory import CA_FILE, build_client, connect_blocking, tls_context
from app.simulator.device import build_message
from tests.helpers import Listener, publish_once

pytestmark = pytest.mark.integration
NEG = CERT_DIR / "negative"
READINGS = {"temperature_c": 25.0, "humidity_pct": 60.0, "soil_moisture_pct": 40.0}


def _msg(device_id: str) -> str:
    return json.dumps(build_message(device_id, 1, READINGS))


# ---------------------------------------------------------------- TLS (server auth + password)

def test_tls_valid_client_connects_with_tls13_and_ecdsa(tls_broker):
    client = build_client(tls_broker.endpoint, "dev-001")
    result = connect_blocking(client, tls_broker.endpoint)
    try:
        assert result.ok, result.reason
        assert result.tls_version == "TLSv1.3"
        assert result.cipher in {"TLS_AES_128_GCM_SHA256", "TLS_AES_256_GCM_SHA384", "TLS_CHACHA20_POLY1305_SHA256"}
        peer = client.socket().getpeercert()
        assert dict(x[0] for x in peer["subject"])["commonName"] == "localhost"
    finally:
        client.disconnect()
        client.loop_stop()


def test_tls_end_to_end_message_delivery(tls_broker):
    ep = tls_broker.endpoint
    listener = Listener(ep, "gateway", "ingest/+")
    try:
        publish_once(ep, "dev-001", "ingest/dev-001", _msg("dev-001"))
        assert listener.wait_for(1)
    finally:
        listener.close()


def test_tls12_also_works_with_ecdhe_ecdsa(tls_broker):
    ctx = tls_context("tls", "dev-001")
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    client = build_client(tls_broker.endpoint, "dev-001", ssl_context=ctx)
    result = connect_blocking(client, tls_broker.endpoint)
    try:
        assert result.ok, result.reason
        assert result.tls_version == "TLSv1.2"
        assert result.cipher.startswith("ECDHE-ECDSA-")
    finally:
        client.disconnect()
        client.loop_stop()


def test_connect_by_ip_matches_san(tls_broker):
    ep = BrokerEndpoint("tls", "127.0.0.1", tls_broker.endpoint.port)
    client = build_client(ep, "dev-001")
    result = connect_blocking(client, ep)
    client.disconnect()
    client.loop_stop()
    assert result.ok, result.reason


def test_client_rejects_untrusted_broker(tls_broker):
    """Client trusts only the ROGUE CA, so our (real) broker certificate must fail verification."""
    ctx = tls_context("tls", "dev-001", ca_file=NEG / "rogue_ca.crt")
    client = build_client(tls_broker.endpoint, "dev-001", ssl_context=ctx)
    result = connect_blocking(client, tls_broker.endpoint, timeout=5)
    assert not result.ok
    assert "certificate verification failed" in result.reason


def test_hostname_mismatch_rejected(wronghost_broker):
    """Broker cert is signed by OUR CA but issued for wrong.example -> hostname check must fail."""
    client = build_client(wronghost_broker.endpoint, "dev-001")
    result = connect_blocking(client, wronghost_broker.endpoint, timeout=5)
    assert not result.ok
    assert "hostname mismatch" in result.reason.lower() or "certificate verification failed" in result.reason


def test_tls_wrong_password_rejected(tls_broker):
    client = build_client(tls_broker.endpoint, "dev-001", password="wrong")
    result = connect_blocking(client, tls_broker.endpoint, timeout=5)
    assert not result.ok
    assert "not authori" in result.reason.lower()


def test_plaintext_client_cannot_use_tls_port(tls_broker):
    plain_on_tls_port = BrokerEndpoint("plain", "localhost", tls_broker.endpoint.port)
    client = build_client(plain_on_tls_port, "dev-001")
    assert not connect_blocking(client, plain_on_tls_port, timeout=3).ok


# ---------------------------------------------------------------- mTLS (client certificates)

def test_mtls_valid_device_connects_and_cn_is_username(mtls_broker):
    ep = mtls_broker.endpoint
    listener = Listener(ep, "gateway", "ingest/+")
    try:
        # The ACL only lets user "dev-001" write ingest/dev-001. Delivery proves the CN became the username.
        publish_once(ep, "dev-001", "ingest/dev-001", _msg("dev-001"))
        assert listener.wait_for(1)
    finally:
        listener.close()


def test_mtls_device_cannot_impersonate_another_device(mtls_broker):
    ep = mtls_broker.endpoint
    listener = Listener(ep, "gateway", "ingest/+")
    try:
        publish_once(ep, "dev-001", "ingest/dev-002", _msg("dev-002"))
        assert not listener.wait_for(1, timeout=1.5)
    finally:
        listener.close()


def test_mtls_no_client_cert_rejected(mtls_broker):
    ctx = tls_context("tls", "dev-001")  # server-auth-only context: no client certificate loaded
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    client.tls_set_context(ctx)
    result = connect_blocking(client, mtls_broker.endpoint, timeout=5)
    assert not result.ok, "broker accepted a client without a certificate"


@pytest.mark.parametrize(
    "stem, why",
    [
        ("rogue_client", "signed by an untrusted CA"),
        ("expired_client", "expired"),
        ("server_as_client", "issued for serverAuth, not clientAuth"),
    ],
)
def test_mtls_bad_client_certificates_rejected(mtls_broker, stem, why):
    ctx = tls_context("mtls", "dev-001", cert_file=NEG / f"{stem}.crt", key_file=NEG / f"{stem}.key")
    client = build_client(mtls_broker.endpoint, "dev-001", ssl_context=ctx)
    result = connect_blocking(client, mtls_broker.endpoint, timeout=5)
    assert not result.ok, f"broker accepted a client certificate that is {why}"


# ---------------------------------------------------------------- static checks

INSECURE_PATTERNS = [
    r"tls_insecure_set\(\s*True",
    r"CERT_NONE",
    r"check_hostname\s*=\s*False",
    r"_create_unverified_context",
    r"verify\s*=\s*False",
]


def test_no_insecure_tls_settings_in_source():
    offenders = []
    for path in list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pat in INSECURE_PATTERNS:
            if re.search(pat, text):
                offenders.append(f"{path.relative_to(ROOT)}: {pat}")
    assert not offenders, offenders


def test_client_context_is_strict():
    ctx = tls_context("tls", "dev-001")
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2
    assert CA_FILE.exists()
