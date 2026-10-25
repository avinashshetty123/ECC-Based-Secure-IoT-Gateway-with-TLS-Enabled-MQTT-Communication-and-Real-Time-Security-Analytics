"""Unit tests for the Mosquitto log parser, using real lines captured from Mosquitto 2.1.2 in this project."""
from app.analytics.broker_log import parse_line
from app.analytics.collector import classify_gateway_event


def _one(line):
    rows = parse_line(line, "mtls")
    assert rows, f"nothing parsed from {line!r}"
    return rows


def test_connected_with_username():
    [(table, row)] = _one("2026-10-23T18:55:55: New client connected from 127.0.0.1:60660 as dev-001-55400 "
                          "(p4, c1, k30, u'dev-001').")
    assert table == "connection_events" and row["event"] == "connected"
    assert row["client_id"] == "dev-001-55400" and row["username"] == "dev-001"


def test_wrong_password():
    rows = _one("2026-10-23T18:55:41: Client attacker-41478 [127.0.0.1:60626] disconnected: not authorised.")
    assert ("security_events", "auth_failed") in [(t, r.get("event_type")) for t, r in rows]
    assert ("connection_events", "rejected") in [(t, r.get("event")) for t, r in rows]


def test_tls_failures_are_classified():
    cases = {
        "error:0A000086:SSL routines::certificate verify failed": "tls_cert_verify_failed",
        "error:0A0000C7:SSL routines::peer did not return a certificate": "tls_no_client_cert",
        "error:0A000418:SSL routines::tlsv1 alert unknown ca": "tls_client_rejected_broker_cert",
        "error:0A00010B:SSL routines::wrong version number": "tls_protocol_mismatch",
    }
    for text, expected in cases.items():
        [(table, row)] = _one(f"2026-10-23T18:55:58: OpenSSL Error while trying to get the error[0]: {text}")
        assert table == "security_events" and row["event_type"] == expected, text


def test_acl_denied_publish():
    [(table, row)] = _one("2026-10-23T18:55:43: Denied PUBLISH from dev-001-40251 (d0, q1, r0, m2, 'ingest/dev-002', "
                          "... (201 bytes))")
    assert row["event_type"] == "acl_denied_publish" and "ingest/dev-002" in row["detail"]


def test_normal_disconnect_and_noise():
    [(table, row)] = _one("2026-10-23T18:37:09: Client gateway-1 [::1:54006] disconnected.")
    assert row["event"] == "disconnected"
    assert parse_line("2026-10-23T18:37:03: Opening ipv4 listen socket on port 1884.", "plain") == []
    assert parse_line("garbage", "plain") == []


def test_gateway_event_classification():
    assert classify_gateway_event({"type": "rejected", "reason": "duplicate/replayed seq 3 (last 4)"}) == "replay_rejected"
    assert classify_gateway_event({"type": "rejected", "reason": "humidity_pct=250.0 outside"}) == "schema_rejected"
    assert classify_gateway_event({"type": "gap", "missing": 2}) == "sequence_gap"
