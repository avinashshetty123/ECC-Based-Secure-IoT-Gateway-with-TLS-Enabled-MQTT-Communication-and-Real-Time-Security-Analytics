"""Unit tests for the visualizer's wire-tap parsers (no broker needed)."""
import json
import socket
import ssl
import threading

from app.mqtt.client_factory import CA_FILE
from app.visualizer.wiretap import MqttStream, TlsStream


def _connect_packet(username: str, password: str, client_id: str = "dev-001-1") -> bytes:
    def s(x: str) -> bytes:
        return len(x).to_bytes(2, "big") + x.encode()
    var = s("MQTT") + bytes([4, 0xC2]) + (30).to_bytes(2, "big")  # level 4, flags: user+pass+clean
    body = var + s(client_id) + s(username) + s(password)
    return bytes([0x10, len(body)]) + body


def test_mqtt_connect_password_is_detected_but_masked():
    secret = "SuperSecretPassw0rd"
    [pkt] = MqttStream().feed(_connect_packet("dev-001", secret))
    assert pkt["rtype"] == "CONNECT"
    assert pkt["fields"]["username"] == "dev-001"
    assert pkt["fields"]["password_exposed"] is True
    assert secret not in json.dumps(pkt), "the real password must never leave the tap"


def test_mqtt_publish_payload_is_readable_and_reframed_across_chunks():
    payload = b'{"temperature_c": 25.1}'
    topic = b"ingest/dev-001"
    body = len(topic).to_bytes(2, "big") + topic + (1).to_bytes(2, "big") + payload
    raw = bytes([0x32, len(body)]) + body  # PUBLISH QoS 1
    stream = MqttStream()
    assert stream.feed(raw[:7]) == []  # incomplete packet -> nothing yet
    [pkt] = stream.feed(raw[7:])
    assert pkt["fields"]["topic"] == "ingest/dev-001"
    assert "25.1" in pkt["readable"]


def test_tls_stream_parses_real_client_hello():
    """Capture a genuine ClientHello produced by Python's ssl module."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    captured = []

    def accept():
        conn, _ = srv.accept()
        captured.append(conn.recv(65536))
        conn.close()

    t = threading.Thread(target=accept)
    t.start()
    ctx = ssl.create_default_context(cafile=str(CA_FILE)) if CA_FILE.exists() else ssl.create_default_context()
    raw = socket.create_connection(srv.getsockname())
    try:
        ctx.wrap_socket(raw, server_hostname="localhost")
    except (ssl.SSLError, OSError):
        pass  # server closes immediately; we only need the ClientHello bytes
    t.join(5)
    srv.close()

    records = TlsStream().feed(captured[0])
    hello = records[0]["handshake"][0]
    assert records[0]["rtype"] == "Handshake"
    assert hello["type"] == "ClientHello"
    assert hello["sni"] == "localhost"
    assert "TLS 1.3" in hello["versions_offered"]
    assert hello["key_shares"], "TLS 1.3 ClientHello must carry an ephemeral ECDHE key share"


def test_non_tls_bytes_are_flagged():
    [rec] = TlsStream().feed(b"\x10\x0c\x00\x04MQTT\x04\x02\x00\x1e")
    assert rec["layer"] == "raw"
