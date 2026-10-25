"""A fleet of 1-20 simulated devices, each with its OWN identity (password or certificate).

  .venv\\Scripts\\python -m app.simulator.fleet --mode mtls --devices 10 --rate 1
  .venv\\Scripts\\python -m app.simulator.fleet --mode mtls --devices 5 --invalid-every 10   # inject bad messages

One scheduler thread publishes for all devices (cheap on an 8 GB laptop);
each device has its own MQTT connection and network thread.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import dataclass, field

from app.config import broker_endpoint, device_ids
from app.mqtt.client_factory import build_client, connect_blocking
from app.simulator.device import SimulatedDevice, build_message
from app.simulator.sensor_models import AgriSensorModel

log = logging.getLogger("fleet")

# Deliberately invalid payloads used to demonstrate gateway validation (security test 7)
INVALID_KINDS = ["out_of_range", "missing_field", "not_json", "wrong_device_id", "wrong_type"]


def invalid_payload(kind: str, device_id: str, seq: int) -> bytes:
    good = build_message(device_id, seq, {"temperature_c": 25.0, "humidity_pct": 50.0, "soil_moisture_pct": 40.0})
    if kind == "out_of_range":
        good["readings"]["humidity_pct"] = 250.0
    elif kind == "missing_field":
        del good["readings"]["temperature_c"]
    elif kind == "not_json":
        return b"temperature=25;humidity=50"
    elif kind == "wrong_device_id":
        good["device_id"] = "dev-999"
    elif kind == "wrong_type":
        good["seq"] = "seven"
    return json.dumps(good).encode()


@dataclass
class FleetStats:
    sent: dict = field(default_factory=dict)        # device_id -> last seq sent
    invalid_sent: int = 0
    connect_ms: dict = field(default_factory=dict)  # device_id -> connection time
    failed: dict = field(default_factory=dict)      # device_id -> reason


class Fleet:
    def __init__(self, mode: str, count: int = 0, qos: int = 1, seed: int | None = None, host: str | None = None,
                 ids: list[str] | None = None):
        """count -> dev-001..dev-<count>; or pass explicit `ids` (e.g. dev-002..dev-009)."""
        self.ids = ids or device_ids(count)
        if not 1 <= len(self.ids) <= 20:
            raise ValueError("devices must be between 1 and 20 (one certificate/password exists per device)")
        self.endpoint = broker_endpoint(mode)
        if host:
            self.endpoint = type(self.endpoint)(mode, host, self.endpoint.port)
        self.qos, self.seed = qos, seed
        self.devices: list[SimulatedDevice] = []
        self.stats = FleetStats()

    def connect(self) -> int:
        for dev_id in self.ids:
            client = build_client(self.endpoint, dev_id, client_id=f"{dev_id}-fleet")
            result = connect_blocking(client, self.endpoint)
            if not result.ok:
                self.stats.failed[dev_id] = result.reason
                log.error("%s could not connect: %s", dev_id, result.reason)
                continue
            self.stats.connect_ms[dev_id] = result.connect_ms
            self.devices.append(SimulatedDevice(dev_id, client, AgriSensorModel(dev_id, seed=self.seed), qos=self.qos))
        log.info("%d/%d devices connected (%s, port %d)", len(self.devices), len(self.ids), self.endpoint.mode,
                 self.endpoint.port)
        return len(self.devices)

    def run(self, rate_hz: float, duration: float = 0, invalid_every: int = 0, stop_event=None,
            on_sent=None) -> None:
        """Publish `rate_hz` messages/s PER DEVICE for `duration` s (0 = until stopped).

        on_sent(msg) is called for every VALID message right after publishing (benchmarks use it
        to know exactly which (device, seq) pairs were sent and when).
        """
        interval = 1.0 / rate_hz
        rng = random.Random(self.seed)
        # Stagger devices so they don't all fire in the same millisecond
        next_due = {d.device_id: time.perf_counter() + i * interval / max(len(self.devices), 1)
                    for i, d in enumerate(self.devices)}
        end = time.perf_counter() + duration if duration else float("inf")
        total = 0
        while time.perf_counter() < end and not (stop_event and stop_event.is_set()):
            dev = min(self.devices, key=lambda d: next_due[d.device_id])
            wait = next_due[dev.device_id] - time.perf_counter()
            if wait > 0:
                time.sleep(min(wait, 0.2))
                continue
            next_due[dev.device_id] += interval
            total += 1
            # Random (but seeded) choice, so faults are spread over all devices instead of
            # always hitting the same one when invalid_every is a multiple of the fleet size.
            if invalid_every and rng.random() < 1.0 / invalid_every:
                kind = rng.choice(INVALID_KINDS)
                dev.client.publish(dev.topic, invalid_payload(kind, dev.device_id, dev.seq + 1), qos=self.qos)
                self.stats.invalid_sent += 1
                log.info("%s sent an INVALID message (%s) on purpose", dev.device_id, kind)
                continue
            msg, _ = dev.publish_next()
            self.stats.sent[dev.device_id] = dev.seq
            if on_sent:
                on_sent(msg)

    def close(self) -> None:
        for d in self.devices:
            d.client.disconnect()
            d.client.loop_stop()


def main() -> int:
    from app.logging_setup import configure

    p = argparse.ArgumentParser(description="Run a fleet of simulated IoT devices")
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="mtls")
    p.add_argument("--devices", type=int, default=10, help="1-20")
    p.add_argument("--rate", type=float, default=1.0, help="messages per second PER device")
    p.add_argument("--duration", type=float, default=0, help="seconds (0 = until Ctrl+C)")
    p.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    p.add_argument("--seed", type=int, default=None, help="deterministic sensor data")
    p.add_argument("--invalid-every", type=int, default=0,
                   help="on average 1 in N messages is deliberately invalid, from a random device (0 = never)")
    args = p.parse_args()
    configure("fleet")

    fleet = Fleet(args.mode, args.devices, qos=args.qos, seed=args.seed)
    if not fleet.connect():
        return 1
    try:
        fleet.run(args.rate, args.duration, args.invalid_every)
    except KeyboardInterrupt:
        pass
    finally:
        fleet.close()
        log.info("sent %d valid + %d invalid messages from %d devices", sum(fleet.stats.sent.values()),
                 fleet.stats.invalid_sent, len(fleet.devices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
