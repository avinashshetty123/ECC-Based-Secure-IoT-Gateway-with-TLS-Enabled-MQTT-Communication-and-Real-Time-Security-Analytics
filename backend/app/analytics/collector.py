"""Collector: turns live MQTT traffic + broker logs + process stats into SQLite rows.

  sensors/+/telemetry  -> readings            (with measured end-to-end latency)
  gateway/events       -> security_events     (schema/replay rejections, gaps, restarts)
  broker log file      -> security_events + connection_events
  psutil               -> resource_samples

Run:  .venv\\Scripts\\python -m app.analytics.collector --mode mtls
"""
from __future__ import annotations

import argparse
import json
import logging
import queue
import threading
import time
from pathlib import Path

from app import clock
from app.analytics import db
from app.analytics.broker_log import parse_line
from app.analytics.resources import ResourceSampler
from app.config import DB_PATH, LOG_DIR, TOPIC_GATEWAY_EVENTS, TOPIC_TELEMETRY_ALL, broker_endpoint
from app.mqtt.client_factory import build_client, connect_blocking

log = logging.getLogger("collector")


def classify_gateway_event(ev: dict) -> str:
    if ev.get("type") == "rejected":
        return "replay_rejected" if "duplicate" in ev.get("reason", "") else "schema_rejected"
    return {"gap": "sequence_gap", "device_restart": "device_restart"}.get(ev.get("type"), ev.get("type", "gateway_event"))


class Collector:
    def __init__(self, mode: str, db_path: Path = DB_PATH, broker_log: Path | None = None,
                 sample_resources: bool = True):
        self.mode = mode
        self.endpoint = broker_endpoint(mode)
        self.conn = db.connect(db_path)
        self.broker_log = broker_log or (LOG_DIR / f"mosquitto_{mode}.log")
        self.q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self.counts = {"readings": 0, "security_events": 0, "connection_events": 0, "resource_samples": 0}
        self.client = None
        self.sampler = ResourceSampler(lambda rows: [self.q.put(("resource_samples", r)) for r in rows]) \
            if sample_resources else None

    # ------------------------------------------------------------------ MQTT
    def _on_connect(self, c, userdata, flags, rc, props):
        c.subscribe([(TOPIC_TELEMETRY_ALL, 1), (TOPIC_GATEWAY_EVENTS, 1)])

    def _on_message(self, c, userdata, msg):
        now_ns, now = clock.mono_ns(), clock.wall()
        try:
            data = json.loads(msg.payload)
        except ValueError:
            log.warning("unparseable message on %s", msg.topic)
            return
        if msg.topic == TOPIC_GATEWAY_EVENTS:
            self.q.put(("security_events", {
                "ts": data.get("ts", now), "source": "gateway", "event_type": classify_gateway_event(data),
                "client_id": None, "device_id": data.get("device_id"),
                "detail": data.get("reason") or json.dumps({k: v for k, v in data.items() if k not in ("ts", "type")}),
                "mode": self.mode}))
            return
        r = data.get("readings", {})
        self.q.put(("readings", {
            "device_id": data.get("device_id"), "seq": data.get("seq"), "ts_sent": data.get("ts_sent"),
            "ts_received": now, "latency_ms": clock.latency_ms(data["ts_mono_ns"], now_ns),
            "gw_latency_ms": (data.get("gateway") or {}).get("gw_latency_ms"),
            "temperature_c": r.get("temperature_c"), "humidity_pct": r.get("humidity_pct"),
            "soil_moisture_pct": r.get("soil_moisture_pct"), "simulated": int(bool(data.get("simulated"))),
            "mode": self.mode}))

    # ------------------------------------------------------------------ broker log tail
    def _tail_broker_log(self) -> None:
        while not self.broker_log.exists() and not self._stop.is_set():
            time.sleep(0.5)
        with open(self.broker_log, encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # only NEW lines: history from earlier runs is not re-imported
            while not self._stop.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                for table, row in parse_line(line, self.mode):
                    self.q.put((table, row))

    # ------------------------------------------------------------------ writer
    def _writer(self) -> None:
        while not self._stop.is_set() or not self.q.empty():
            batch: dict[str, list] = {}
            try:
                table, row = self.q.get(timeout=0.5)
                batch.setdefault(table, []).append(row)
                while len(batch.get(table, [])) < 500:
                    table, row = self.q.get_nowait()
                    batch.setdefault(table, []).append(row)
            except queue.Empty:
                pass
            for table, rows in batch.items():
                db.insert_many(self.conn, table, rows)
                self.counts[table] += len(rows)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        threading.Thread(target=self._writer, daemon=True).start()
        threading.Thread(target=self._tail_broker_log, daemon=True).start()
        if self.sampler:
            self.sampler.start()
        delay = 1.0
        while not self._stop.is_set():
            self.client = build_client(self.endpoint, "collector", client_id="collector")
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            result = connect_blocking(self.client, self.endpoint)
            if result.ok:
                log.info("connected (%s, %s); writing to %s", self.mode, result.tls_version or "plain", DB_PATH.name)
                return True
            log.warning("connect failed: %s - retrying in %.0f s", result.reason, delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        return False

    def stop(self) -> None:
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
        if self.sampler:
            self.sampler.stop()
        self._stop.set()
        time.sleep(0.8)  # let the writer flush


def main() -> int:
    from app.logging_setup import configure

    p = argparse.ArgumentParser(description="Store telemetry, security events and metrics in SQLite")
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="mtls")
    p.add_argument("--broker-log", type=Path, default=None, help="Mosquitto log file to watch")
    args = p.parse_args()
    configure("collector")
    c = Collector(args.mode, broker_log=args.broker_log)
    c.start()
    try:
        while True:
            time.sleep(15)
            log.info("stored so far: %s", c.counts)
    except KeyboardInterrupt:
        pass
    finally:
        c.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
