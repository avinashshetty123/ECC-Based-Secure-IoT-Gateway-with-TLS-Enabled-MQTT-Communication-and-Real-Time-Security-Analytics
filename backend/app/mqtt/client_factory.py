"""The ONE place where MQTT clients are built, for all three broker modes.

Security guarantees enforced here (and checked by tests):
  * TLS modes always use CERT_REQUIRED + hostname verification.
  * TLS 1.2 is the minimum protocol version.
  * paho's "insecure" TLS switch (skip hostname check) is never enabled;
    tests/test_tls_security.py scans the source to enforce this.
  * mTLS clients authenticate with a certificate (CN = MQTT username), not a password.
"""
from __future__ import annotations

import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from app.config import CERT_DIR, BrokerEndpoint, password_for

CA_FILE = CERT_DIR / "ca" / "ca.crt"


def client_cert_paths(identity: str) -> tuple[Path, Path]:
    return CERT_DIR / "clients" / f"{identity}.crt", CERT_DIR / "clients" / f"{identity}.key"


def tls_context(
    mode: str,
    identity: str,
    ca_file: Path | None = None,
    cert_file: Path | None = None,
    key_file: Path | None = None,
) -> ssl.SSLContext:
    """Build a strict client-side TLS context.

    ca_file/cert_file/key_file overrides exist so tests can present untrusted
    or mismatched certificates; verification itself can never be turned off.
    """
    ca = Path(ca_file or CA_FILE)
    if not ca.exists():
        raise FileNotFoundError(f"CA certificate {ca} missing. Run scripts\\gen_certs.ps1 first.")
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    if mode == "mtls":
        default_crt, default_key = client_cert_paths(identity)
        ctx.load_cert_chain(certfile=str(cert_file or default_crt), keyfile=str(key_file or default_key))
    return ctx


def build_client(
    endpoint: BrokerEndpoint,
    identity: str,
    client_id: str | None = None,
    password: str | None = None,
    ssl_context: ssl.SSLContext | None = None,
) -> mqtt.Client:
    """Create a configured (not yet connected) paho client.

    identity  - MQTT username (plain/tls) or certificate CN (mtls).
    password  - override for negative tests; default comes from credentials.json.
    """
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id or f"{identity}-{int(time.time() * 1000) % 10_000_000}",
        protocol=mqtt.MQTTv311,
        clean_session=True,
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    if endpoint.mode in ("plain", "tls"):
        client.username_pw_set(identity, password if password is not None else password_for(identity))
    if endpoint.mode in ("tls", "mtls"):
        client.tls_set_context(ssl_context or tls_context(endpoint.mode, identity))
    return client


@dataclass
class ConnectResult:
    ok: bool
    connect_ms: float | None  # connect() call -> CONNACK, incl. TCP + TLS handshake
    reason: str
    tls_version: str | None = None  # e.g. "TLSv1.3" (None for plain TCP)
    cipher: str | None = None  # e.g. "TLS_AES_128_GCM_SHA256"


def _tls_details(client: mqtt.Client) -> tuple[str | None, str | None]:
    sock = client.socket()
    if isinstance(sock, ssl.SSLSocket):
        cipher = sock.cipher()
        return sock.version(), cipher[0] if cipher else None
    return None, None


def connect_blocking(
    client: mqtt.Client, endpoint: BrokerEndpoint, timeout: float = 10.0, keepalive: int = 30
) -> ConnectResult:
    """Connect, start the network loop, and wait for CONNACK.

    On failure the network loop is stopped so paho does not keep retrying
    with bad credentials. On success paho's automatic reconnect stays active.
    """
    done = threading.Event()
    outcome: dict = {}
    user_on_connect = client.on_connect
    user_on_disconnect = client.on_disconnect

    def _on_connect(c, userdata, flags, reason_code, properties):
        outcome.setdefault("connack", reason_code)
        done.set()
        if user_on_connect and not reason_code.is_failure:
            user_on_connect(c, userdata, flags, reason_code, properties)

    def _on_disconnect(c, userdata, flags, reason_code, properties):
        # Without a CONNACK this means the broker dropped us during the
        # handshake (e.g. rejected client certificate in TLS 1.3).
        outcome.setdefault("disconnect", reason_code)
        done.set()

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    t0 = time.perf_counter()
    try:
        client.connect(endpoint.host, endpoint.port, keepalive)
    except ssl.SSLCertVerificationError as exc:
        return ConnectResult(False, None, f"certificate verification failed: {exc.verify_message}")
    except ssl.SSLError as exc:
        return ConnectResult(False, None, f"TLS error: {exc.reason or exc}")
    except (ConnectionRefusedError, TimeoutError, OSError) as exc:
        return ConnectResult(False, None, f"network error: {exc}")
    client.loop_start()

    if not done.wait(timeout):
        client.loop_stop()
        return ConnectResult(False, None, "timeout waiting for CONNACK")
    elapsed_ms = (time.perf_counter() - t0) * 1000

    connack = outcome.get("connack")
    if connack is None or connack.is_failure:
        client.loop_stop()
        sock = client.socket()
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        client.on_connect, client.on_disconnect = user_on_connect, user_on_disconnect
        reason = f"refused: {connack}" if connack is not None else "connection dropped by broker before CONNACK"
        return ConnectResult(False, None, reason)

    client.on_connect, client.on_disconnect = user_on_connect, user_on_disconnect
    return ConnectResult(True, elapsed_ms, "connected", *_tls_details(client))
