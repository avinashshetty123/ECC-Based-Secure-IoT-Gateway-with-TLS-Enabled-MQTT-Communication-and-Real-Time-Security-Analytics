"""Secure gateway: validate device messages and forward the good ones.

    ingest/<id>  --(validate + sequence check)-->  sensors/<id>/telemetry
                                         +------>  gateway/events  (rejections, gaps, restarts)

Run:  .venv\\Scripts\\python -m app.gateway --mode mtls
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from typing import Callable

from app import clock
from app.config import TOPIC_GATEWAY_EVENTS, TOPIC_INGEST_ALL, TOPIC_TELEMETRY, BrokerEndpoint
from app.gateway.schema import SequenceTracker, validate
from app.mqtt.client_factory import build_client, connect_blocking

log = logging.getLogger("gateway")


class Gateway:
    def __init__(self, endpoint: BrokerEndpoint, identity: str = "gateway", qos: int = 1,
                 on_event: Callable[[str, dict], None] | None = None, client_id: str | None = None):
        self.endpoint = endpoint
        self.identity = identity
        self.qos = qos
        self.on_event = on_event  # hook for the visualizer / tests: (kind, details)
        self.client_id = client_id or "gateway"
        self.seq = SequenceTracker()
        self.stats = Counter()
        self.client = None
        self.connected = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    def start(self, retries: int | None = None, max_backoff: float = 30.0) -> bool:
        """Connect (retrying with exponential backoff). retries=None retries forever."""
        attempt, delay = 0, 1.0
        while True:
            attempt += 1
            self.client = build_client(self.endpoint, self.identity, client_id=self.client_id)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
            result = connect_blocking(self.client, self.endpoint)
            if result.ok:
                log.info("connected to %s:%s mode=%s %s in %.1f ms", self.endpoint.host, self.endpoint.port,
                         self.endpoint.mode, result.tls_version or "plain", result.connect_ms)
                return True
            log.warning("connect attempt %d failed: %s", attempt, result.reason)
            if retries is not None and attempt > retries:
                return False
            time.sleep(delay)
            delay = min(delay * 2, max_backoff)

    def stop(self) -> None:
        if self.client is not None:
            self.client.disconnect()
            self.client.loop_stop()
        self.connected.clear()

    # ------------------------------------------------------------------ callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe(TOPIC_INGEST_ALL, qos=self.qos)
        self.connected.set()
        if self.stats["connects"]:
            log.info("reconnected and re-subscribed to %s", TOPIC_INGEST_ALL)
        self.stats["connects"] += 1

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected.clear()
        if not reason_code.is_failure:  # we called disconnect() ourselves
            log.info("disconnected from broker (normal shutdown)")
            return
        self.stats["disconnects"] += 1
        log.warning("connection to broker lost (%s); paho will reconnect automatically", reason_code)

    def _on_message(self, client, userdata, msg):
        received_ns = clock.mono_ns()
        with self._lock:
            self.stats["received"] += 1
            result = validate(msg.topic, msg.payload)
            if not result.ok:
                self._reject(msg.topic, len(msg.payload), result.reason)
                return
            data = result.data
            status, detail = self.seq.check(data["device_id"], data["seq"], data["ts_sent"])
            if status == "duplicate":
                self._reject(msg.topic, len(msg.payload), f"duplicate/replayed seq {data['seq']} (last {detail})")
                return
            if status == "gap":
                self.stats["gaps"] += detail
                self._event("gap", device_id=data["device_id"], missing=detail, seq=data["seq"])
            elif status == "restart":
                self._event("device_restart", device_id=data["device_id"], previous_seq=detail)

            data["gateway"] = {"validated": True, "gw_ts": clock.wall(),
                               "gw_latency_ms": round(clock.latency_ms(data["ts_mono_ns"], received_ns), 3)}
            topic = TOPIC_TELEMETRY.format(device_id=data["device_id"])
            self.client.publish(topic, json.dumps(data, separators=(",", ":")), qos=self.qos)
            self.stats["accepted"] += 1
            if self.on_event:
                self.on_event("accepted", {"topic": msg.topic, "forwarded_to": topic, "data": data,
                                           "bytes": len(msg.payload)})

    # ------------------------------------------------------------------ helpers
    def _reject(self, topic: str, size: int, reason: str) -> None:
        self.stats["rejected"] += 1
        self.stats[f"rejected:{reason.split(' ')[0]}"] += 1
        log.warning("REJECTED message on %s (%d B): %s", topic, size, reason)
        self._event("rejected", topic=topic, size=size, reason=reason,
                    device_id=topic.split("/", 1)[1] if "/" in topic else None)

    def _event(self, kind: str, **details) -> None:
        event = {"ts": clock.wall(), "type": kind, **details}
        if self.client is not None:
            self.client.publish(TOPIC_GATEWAY_EVENTS, json.dumps(event, separators=(",", ":")), qos=self.qos)
        if self.on_event:
            self.on_event(kind, event)

    def summary(self) -> str:
        s = self.stats
        return (f"received={s['received']} accepted={s['accepted']} rejected={s['rejected']} "
                f"gaps={s['gaps']} reconnects={max(s['connects'] - 1, 0)}")
