"""Parse Mosquitto log lines into security and connection events.

Pure functions (no I/O), so they are unit-tested against real log lines
captured during Phases 3-5.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}):\s*(.*)$")
CONNECTED = re.compile(r"New client connected from (\S+) as (\S+) \(.*?(?:u'([^']*)')?\)\.?$")
DISCONNECTED = re.compile(r"Client (\S+) \[(\S+)\] disconnected(?:: (.+?))?\.?$")
CLOSED = re.compile(r"Client (\S+) closed its connection\.?$")
DENIED_PUB = re.compile(r"Denied PUBLISH from (\S+) \(.*?'([^']+)'")
OPENSSL = re.compile(r"OpenSSL Error.*?:([^:]+)$")

TLS_TYPES = {
    "certificate verify failed": "tls_cert_verify_failed",
    "peer did not return a certificate": "tls_no_client_cert",
    "tlsv1 alert unknown ca": "tls_client_rejected_broker_cert",
    "wrong version number": "tls_protocol_mismatch",
    "unsupported protocol": "tls_protocol_mismatch",
    "no shared cipher": "tls_no_shared_cipher",
}


def parse_line(line: str, mode: str) -> list[tuple[str, dict]]:
    """Return a list of (table, row) produced by one log line."""
    m = TS.match(line.strip())
    if not m:
        return []
    try:
        ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").timestamp()
    except ValueError:
        ts = time.time()
    msg = m.group(2)
    out: list[tuple[str, dict]] = []

    if c := CONNECTED.search(msg):
        out.append(("connection_events", {"ts": ts, "client_id": c.group(2), "username": c.group(3),
                                          "event": "connected", "detail": c.group(1), "mode": mode}))
    elif d := DISCONNECTED.search(msg):
        reason = (d.group(3) or "").strip()
        if reason in ("not authorised", "not authorized"):
            out.append(("security_events", {"ts": ts, "source": "broker_log", "event_type": "auth_failed",
                                            "client_id": d.group(1), "device_id": None,
                                            "detail": f"login refused from {d.group(2)}", "mode": mode}))
            out.append(("connection_events", {"ts": ts, "client_id": d.group(1), "username": None,
                                              "event": "rejected", "detail": "not authorised", "mode": mode}))
        elif reason == "protocol error":
            # TLS handshake failures: the specific reason is on the preceding OpenSSL line
            out.append(("connection_events", {"ts": ts, "client_id": d.group(1), "username": None,
                                              "event": "rejected", "detail": "TLS/protocol error", "mode": mode}))
        else:
            out.append(("connection_events", {"ts": ts, "client_id": d.group(1), "username": None,
                                              "event": "disconnected", "detail": reason or "normal", "mode": mode}))
    elif c := CLOSED.search(msg):
        out.append(("connection_events", {"ts": ts, "client_id": c.group(1), "username": None,
                                          "event": "disconnected", "detail": "closed by client", "mode": mode}))
    elif d := DENIED_PUB.search(msg):
        out.append(("security_events", {"ts": ts, "source": "broker_log", "event_type": "acl_denied_publish",
                                        "client_id": d.group(1), "device_id": None,
                                        "detail": f"publish to {d.group(2)} denied by ACL", "mode": mode}))
    elif o := OPENSSL.search(msg):
        text = o.group(1).strip()
        etype = next((v for k, v in TLS_TYPES.items() if k in text), "tls_error")
        out.append(("security_events", {"ts": ts, "source": "broker_log", "event_type": etype, "client_id": None,
                                        "device_id": None, "detail": text, "mode": mode}))
    return out
