"""A single simulated IoT device.

Run one device (Phase 3 prototype):
  .venv\\Scripts\\python -m app.simulator.device --mode plain --device-id dev-001 --count 10
"""
from __future__ import annotations

import argparse
import json
import logging
import time

import paho.mqtt.client as mqtt

from app import clock
from app.config import TOPIC_INGEST, broker_endpoint
from app.mqtt.client_factory import build_client, connect_blocking
from app.simulator.sensor_models import AgriSensorModel

SCHEMA_VERSION = 1
log = logging.getLogger("device")


def build_message(device_id: str, seq: int, readings: dict[str, float], ts_sent: float | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "device_id": device_id,
        "seq": seq,
        "ts_sent": clock.wall() if ts_sent is None else ts_sent,  # for display
        "ts_mono_ns": clock.mono_ns(),  # for latency (same-host only, see app/clock.py)
        "simulated": True,
        "readings": readings,
    }


class SimulatedDevice:
    def __init__(self, device_id: str, client: mqtt.Client, model: AgriSensorModel, qos: int = 1):
        self.device_id = device_id
        self.client = client
        self.model = model
        self.qos = qos
        self.topic = TOPIC_INGEST.format(device_id=device_id)
        self.seq = 0

    def publish_next(self) -> tuple[dict, mqtt.MQTTMessageInfo]:
        self.seq += 1
        now = clock.wall()
        msg = build_message(self.device_id, self.seq, self.model.read(now), ts_sent=now)
        info = self.client.publish(self.topic, json.dumps(msg, separators=(",", ":")), qos=self.qos)
        return msg, info


def main() -> int:
    p = argparse.ArgumentParser(description="Run one simulated device")
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="plain")
    p.add_argument("--device-id", default="dev-001")
    p.add_argument("--count", type=int, default=10, help="messages to send (0 = forever)")
    p.add_argument("--interval", type=float, default=1.0, help="seconds between messages")
    p.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    p.add_argument("--seed", type=int, default=None, help="deterministic readings")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    endpoint = broker_endpoint(args.mode)
    client = build_client(endpoint, args.device_id)
    result = connect_blocking(client, endpoint)
    if not result.ok:
        log.error("Connection failed (%s:%s, mode=%s): %s", endpoint.host, endpoint.port, endpoint.mode, result.reason)
        return 1
    log.info("Connected to %s:%s mode=%s in %.1f ms", endpoint.host, endpoint.port, endpoint.mode, result.connect_ms)

    device = SimulatedDevice(args.device_id, client, AgriSensorModel(args.device_id, seed=args.seed), qos=args.qos)
    try:
        while args.count == 0 or device.seq < args.count:
            msg, info = device.publish_next()
            info.wait_for_publish(timeout=5)
            log.info("published seq=%d %s", msg["seq"], msg["readings"])
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
