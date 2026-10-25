"""Message validation for device -> gateway messages (schema_version 1).

The gateway trusts NOTHING in the payload: TLS proves who sent the bytes,
the broker ACL proves the device wrote to its own topic, and this module
proves the content is well-formed and physically plausible.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

MAX_PAYLOAD_BYTES = 1024
SCHEMA_VERSION = 1
DEVICE_ID_RE = re.compile(r"^dev-\d{3}$")
TOPIC_RE = re.compile(r"^ingest/(dev-\d{3})$")

# Physical sensor ranges (typical capacitive soil / DHT-class sensors)
READING_RANGES = {
    "temperature_c": (-40.0, 85.0),
    "humidity_pct": (0.0, 100.0),
    "soil_moisture_pct": (0.0, 100.0),
}
TOP_LEVEL = {"schema_version", "device_id", "seq", "ts_sent", "ts_mono_ns", "simulated", "readings"}


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    data: dict = field(default_factory=dict)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)) and math.isfinite(v)


def validate(topic: str, payload: bytes) -> ValidationResult:
    if len(payload) > MAX_PAYLOAD_BYTES:
        return ValidationResult(False, f"payload too large ({len(payload)} B > {MAX_PAYLOAD_BYTES} B)")
    m = TOPIC_RE.match(topic)
    if not m:
        return ValidationResult(False, f"unexpected topic {topic!r}")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ValidationResult(False, "not valid UTF-8 JSON")
    if not isinstance(data, dict):
        return ValidationResult(False, "JSON root must be an object")

    missing = TOP_LEVEL - data.keys()
    if missing:
        return ValidationResult(False, f"missing field(s): {', '.join(sorted(missing))}")
    extra = data.keys() - TOP_LEVEL
    if extra:
        return ValidationResult(False, f"unexpected field(s): {', '.join(sorted(extra))}")

    if data["schema_version"] != SCHEMA_VERSION or not _is_int(data["schema_version"]):
        return ValidationResult(False, f"unsupported schema_version {data['schema_version']!r}")
    if not isinstance(data["device_id"], str) or not DEVICE_ID_RE.match(data["device_id"]):
        return ValidationResult(False, "device_id must look like dev-NNN")
    if data["device_id"] != m.group(1):
        return ValidationResult(False, f"device_id {data['device_id']!r} does not match topic owner {m.group(1)!r}")
    if not _is_int(data["seq"]) or data["seq"] < 1:
        return ValidationResult(False, "seq must be a positive integer")
    if not _is_number(data["ts_sent"]) or data["ts_sent"] <= 0:
        return ValidationResult(False, "ts_sent must be a positive number")
    if not _is_int(data["ts_mono_ns"]) or data["ts_mono_ns"] < 0:
        return ValidationResult(False, "ts_mono_ns must be a non-negative integer")
    if not isinstance(data["simulated"], bool):
        return ValidationResult(False, "simulated must be true/false")

    readings = data["readings"]
    if not isinstance(readings, dict) or set(readings) != set(READING_RANGES):
        return ValidationResult(False, f"readings must contain exactly {', '.join(READING_RANGES)}")
    for key, (lo, hi) in READING_RANGES.items():
        v = readings[key]
        if not _is_number(v):
            return ValidationResult(False, f"{key} must be a finite number")
        if not lo <= v <= hi:
            return ValidationResult(False, f"{key}={v} outside physical range [{lo}, {hi}]")
    return ValidationResult(True, "", data)


class SequenceTracker:
    """Per-device sequence checks: duplicates/replays are rejected, gaps are reported.

    A device that reboots starts again at seq 1. That is accepted as a restart ONLY
    if the message is also newer (ts_sent) than the last one seen; otherwise a
    captured early message could be replayed and pass as a "restart".
    """

    def __init__(self):
        self.last: dict[str, tuple[int, float]] = {}  # device -> (seq, ts_sent)

    def check(self, device_id: str, seq: int, ts_sent: float) -> tuple[str, int]:
        """Return (status, detail): status in new | gap | restart | duplicate."""
        prev = self.last.get(device_id)
        if prev is None:
            self.last[device_id] = (seq, ts_sent)
            return "new", 0
        prev_seq, prev_ts = prev
        if seq == prev_seq + 1:
            self.last[device_id] = (seq, ts_sent)
            return "new", 0
        if seq == 1 and ts_sent > prev_ts:
            self.last[device_id] = (seq, ts_sent)
            return "restart", prev_seq
        if seq <= prev_seq:
            return "duplicate", prev_seq
        self.last[device_id] = (seq, ts_sent)
        return "gap", seq - prev_seq - 1
