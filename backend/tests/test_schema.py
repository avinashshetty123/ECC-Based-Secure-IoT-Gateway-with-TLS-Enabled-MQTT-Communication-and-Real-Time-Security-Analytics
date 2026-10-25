"""Unit tests for gateway message validation (security test 7) and sequence tracking."""
import json

import pytest

from app.gateway.schema import MAX_PAYLOAD_BYTES, SequenceTracker, validate
from app.simulator.device import build_message
from app.simulator.fleet import INVALID_KINDS, invalid_payload

GOOD_READINGS = {"temperature_c": 25.0, "humidity_pct": 60.0, "soil_moisture_pct": 40.0}


def _payload(**overrides) -> bytes:
    msg = build_message("dev-001", 1, dict(GOOD_READINGS))
    for k, v in overrides.items():
        if k.startswith("r_"):
            msg["readings"][k[2:]] = v
        else:
            msg[k] = v
    return json.dumps(msg).encode()


def test_valid_message_passes():
    r = validate("ingest/dev-001", _payload())
    assert r.ok, r.reason
    assert r.data["device_id"] == "dev-001"


@pytest.mark.parametrize("payload, reason_part", [
    (b"not json at all", "JSON"),
    (b"[1, 2, 3]", "object"),
    (_payload(r_humidity_pct=250.0), "outside physical range"),
    (_payload(r_temperature_c=-80), "outside physical range"),
    (_payload(r_soil_moisture_pct="wet"), "finite number"),
    (_payload(r_temperature_c=float("nan")), "JSON"),            # NaN is not valid JSON for json.loads? (Python allows it) - see below
    (_payload(seq=0), "seq"),
    (_payload(seq="7"), "seq"),
    (_payload(seq=True), "seq"),                                  # bool is not an int here
    (_payload(schema_version=2), "schema_version"),
    (_payload(device_id="dev-002"), "does not match topic"),
    (_payload(device_id="sensor-1"), "dev-NNN"),
    (_payload(simulated="yes"), "simulated"),
    (_payload(extra_field=1), "unexpected field"),
])
def test_invalid_messages_rejected(payload, reason_part):
    r = validate("ingest/dev-001", payload)
    assert not r.ok
    # Python's json accepts NaN; our range/finite check must still catch it
    if b"NaN" in payload:
        assert "finite" in r.reason
    else:
        assert reason_part in r.reason, r.reason


def test_missing_field_rejected():
    msg = json.loads(_payload())
    del msg["ts_mono_ns"]
    r = validate("ingest/dev-001", json.dumps(msg).encode())
    assert not r.ok and "missing" in r.reason


def test_oversized_payload_rejected():
    r = validate("ingest/dev-001", b"x" * (MAX_PAYLOAD_BYTES + 1))
    assert not r.ok and "too large" in r.reason


def test_unexpected_topic_rejected():
    assert not validate("sensors/dev-001/telemetry", _payload()).ok


@pytest.mark.parametrize("kind", INVALID_KINDS)
def test_fleet_invalid_payloads_are_all_rejected(kind):
    assert not validate("ingest/dev-001", invalid_payload(kind, "dev-001", 5)).ok


def test_sequence_tracker():
    t = SequenceTracker()
    assert t.check("dev-001", 1, 100.0) == ("new", 0)
    assert t.check("dev-001", 2, 101.0) == ("new", 0)
    assert t.check("dev-001", 2, 101.0) == ("duplicate", 2)   # replay
    assert t.check("dev-001", 5, 104.0) == ("gap", 2)         # 3 and 4 missing
    assert t.check("dev-001", 4, 103.0) == ("duplicate", 5)   # late / out of order
    assert t.check("dev-001", 1, 100.0) == ("duplicate", 5)   # replay of the FIRST message is not a "restart"
    assert t.check("dev-001", 1, 200.0) == ("restart", 5)     # genuine reboot: seq 1 but newer
    assert t.check("dev-002", 9, 50.0) == ("new", 0)          # independent per device
