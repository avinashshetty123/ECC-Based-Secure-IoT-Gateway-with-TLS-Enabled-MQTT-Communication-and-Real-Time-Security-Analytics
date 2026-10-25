"""One live demo session: broker + wire tap + gateway listener + a device.

    dev-001 / attackers ──▶ WireTap (eavesdropper view) ──▶ Mosquitto ──▶ gateway listener
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ec

from app import clock
from app.config import (CERT_DIR, LOG_DIR, MOSQUITTO_DIR, ROOT, TOPIC_INGEST_ALL, BrokerEndpoint,
                        broker_endpoint)
from app.analytics.collector import Collector
from app.config import device_ids
from app.gateway.gateway import Gateway
from app.simulator.fleet import Fleet
from app.mqtt.client_factory import build_client, client_cert_paths, connect_blocking
from app.simulator.device import SimulatedDevice, build_message
from app.simulator.sensor_models import AgriSensorModel
from app.visualizer.events import EventBus
from app.visualizer.wiretap import WireTap
from app.winjob import kill_with_parent

TAP_PORTS = {"plain": 11884, "tls": 18883, "mtls": 18884}
DEVICE_ID = "dev-001"
VISUAL_TOPIC = f"ingest/{DEVICE_ID}"
# Per-packet broker debug lines are only interesting for the animated device (client id dev-001-<n>)
NOISY_LOG = re.compile(r"(Received|Sending) (PUBLISH|PUBACK|PUBREC|PUBREL|PUBCOMP|SUBSCRIBE|SUBACK)")
VISUAL_LOG = re.compile(r"\bdev-001-\d+\b|'ingest/dev-001'|Denied")


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def describe_cert(cert: x509.Certificate) -> dict:
    def cn(name: x509.Name) -> str:
        attrs = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        return attrs[0].value if attrs else name.rfc4514_string()

    key = cert.public_key()
    info = {
        "subject_cn": cn(cert.subject),
        "issuer_cn": cn(cert.issuer),
        "key": f"EC {key.curve.name} ({key.curve.key_size}-bit)" if isinstance(key, ec.EllipticCurvePublicKey) else type(key).__name__,
        "signature": cert.signature_algorithm_oid._name,
        "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        "serial": f"{cert.serial_number:x}"[:16] + "…",
    }
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        info["san"] = [str(v) for v in san.get_values_for_type(x509.DNSName)] + \
                      [str(v) for v in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        info["san"] = []
    try:
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        info["purpose"] = [u._name for u in eku]
    except x509.ExtensionNotFound:
        pass
    return info


class BrokerLogTail(threading.Thread):
    SECURITY = re.compile(r"not authori|verify failed|did not return a certificate|unknown ca|protocol error|"
                          r"Denied|bad user|wrong version|alert", re.I)
    OK = re.compile(r"New client connected", re.I)

    def __init__(self, bus: EventBus, path: Path):
        super().__init__(daemon=True)
        self.bus, self.path, self._stop = bus, path, threading.Event()

    def run(self) -> None:
        while not self.path.exists() and not self._stop.is_set():
            time.sleep(0.1)
        with open(self.path, encoding="utf-8", errors="replace") as f:
            while not self._stop.is_set():
                line = f.readline()
                if not line:
                    time.sleep(0.15)
                    continue
                line = line.rstrip()
                # Keep-alive chatter is noise for a live demo
                if not line or re.search(r"PINGREQ|PINGRESP", line):
                    continue
                if NOISY_LOG.search(line) and not VISUAL_LOG.search(line):
                    continue  # fleet / collector traffic: stored in SQLite, not animated
                level = "security" if self.SECURITY.search(line) else "ok" if self.OK.search(line) else "info"
                self.bus.publish("broker_log", line=line, level=level)

    def stop(self) -> None:
        self._stop.set()


class DemoSession:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.mode: str | None = None
        self.lock = threading.RLock()
        self.broker: subprocess.Popen | None = None
        self.tap: WireTap | None = None
        self.log_tail: BrokerLogTail | None = None
        self.gateway = None
        self.device_client = None
        self.device: SimulatedDevice | None = None
        self.streaming = False
        self._stream_thread: threading.Thread | None = None
        self.last_rx: dict[str, float] = {}  # topic -> time the gateway last ACCEPTED it
        self.last_reject: tuple[str, str, float] | None = None  # (topic, reason, time)
        self.last_sent: tuple[str, str] | None = None  # (topic, exact payload) - used by the replay scenario
        self.starting = False
        self.broker_log_path: Path | None = None
        self.collector: Collector | None = None   # stores telemetry/events/metrics in SQLite for the analytics page
        self.fleet: Fleet | None = None           # optional extra devices (dev-002...) connected directly
        self.fleet_stop = threading.Event()
        self.fleet_info: dict | None = None

    # ------------------------------------------------------------------ endpoints
    @property
    def broker_ep(self) -> BrokerEndpoint:
        return broker_endpoint(self.mode)

    @property
    def tap_ep(self) -> BrokerEndpoint:
        return BrokerEndpoint(self.mode, "localhost", TAP_PORTS[self.mode])

    def state(self) -> dict:
        return {"mode": self.mode, "running": self.broker is not None and self.broker.poll() is None,
                "streaming": self.streaming, "fleet": self.fleet_info,
                "broker_port": self.broker_ep.port if self.mode else None,
                "tap_port": TAP_PORTS.get(self.mode) if self.mode else None}

    # ------------------------------------------------------------------ lifecycle
    def start(self, mode: str) -> None:
        self.starting = True
        try:
            self._start(mode)
        finally:
            self.starting = False

    def _start(self, mode: str) -> None:
        with self.lock:
            self.stop()
            self.mode = mode
            self.bus.publish("session", state="starting", **self.state())
            try:
                self._start_broker()
                self.tap = WireTap(self.bus, TAP_PORTS[mode], self.broker_ep.port, tls=mode != "plain")
                self.tap.start()
                self._start_gateway()
                self.collector = Collector(mode, broker_log=self.broker_log_path)
                self.collector.start()
                self.connect_device()
            except Exception as exc:  # noqa: BLE001 - report any startup problem to the UI
                self.bus.publish("session", state="error", message=str(exc), **self.state())
                self.stop(quiet=True)
                return
            self.bus.publish("session", state="running", **self.state())

        # Send one reading right away so every pipeline stage is demonstrated without extra clicks
        def first_reading():
            time.sleep(1.5)
            with self.lock:
                if self.device_client is not None and self.mode == mode:
                    self.publish_reading()
        threading.Thread(target=first_reading, daemon=True).start()

    def stop(self, quiet: bool = False) -> None:
        with self.lock:
            self.streaming = False
            self._stop_fleet()
            if self.collector is not None:
                try:
                    self.collector.stop()
                except Exception:  # noqa: BLE001
                    pass
                self.collector = None
            if self.gateway is not None:
                try:
                    self.gateway.stop()
                except Exception:  # noqa: BLE001
                    pass
            if self.device_client is not None:
                try:
                    self.device_client.disconnect()
                    self.device_client.loop_stop()
                except Exception:  # noqa: BLE001
                    pass
            self.device_client = self.gateway = self.device = None
            if self.tap:
                self.tap.stop()
                self.tap = None
            if self.log_tail:
                self.log_tail.stop()
                self.log_tail = None
            was_running = self.broker is not None
            if self.broker and self.broker.poll() is None:
                self.broker.terminate()
                try:
                    self.broker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.broker.kill()
            self.broker = None
            if was_running and not quiet:
                self.bus.publish("session", state="stopped", mode=self.mode, running=False, streaming=False)

    def _start_broker(self) -> None:
        port = self.broker_ep.port
        if _port_open(port):
            raise RuntimeError(f"Port {port} is already in use - stop the other broker/test run first.")
        if self.mode != "plain" and not (CERT_DIR / "server" / "server.crt").exists():
            raise RuntimeError("Certificates missing - run scripts\\gen_certs.ps1")
        # Visualizer-specific copy of the real config: same security settings,
        # separate log file, plus 'debug' logging so every PUBLISH / denial is visible.
        src = (ROOT / "config" / f"broker_{self.mode}.conf").read_text(encoding="utf-8")
        log_rel = f"logs/visualizer_{self.mode}.log"
        self.broker_log_path = ROOT / log_rel
        conf = re.sub(r"^log_dest .*$", "", src, flags=re.M)
        conf += f"\nlog_dest file {log_rel}\nlog_type debug\n"
        conf_path = LOG_DIR / "visualizer" / f"broker_{self.mode}.conf"
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(conf, encoding="utf-8")
        (ROOT / log_rel).write_text("", encoding="utf-8")

        self.log_tail = BrokerLogTail(self.bus, ROOT / log_rel)
        self.log_tail.start()
        self.broker = subprocess.Popen(
            [str(MOSQUITTO_DIR / "mosquitto.exe"), "-c", str(conf_path.relative_to(ROOT))],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        kill_with_parent(self.broker)  # closing the visualizer window also stops its broker
        # Wait for Mosquitto's own "running" log line. (Probing the port with a bare
        # TCP connect would itself show up as a TLS "protocol error" in the broker log.)
        deadline = time.time() + 8
        while " running" not in (ROOT / log_rel).read_text(encoding="utf-8", errors="replace"):
            if self.broker.poll() is not None or time.time() > deadline:
                raise RuntimeError(f"Mosquitto failed to start (see {log_rel})")
            time.sleep(0.1)

    def _start_gateway(self) -> None:
        """Run the REAL Phase-5 gateway (validation + replay protection) and mirror its decisions to the UI."""

        def on_event(kind: str, ev: dict) -> None:
            # Only dev-001 (the device on the tapped, animated path) goes to the live UI.
            # Fleet devices dev-002... are stored by the collector and shown on the Analytics page.
            if ev.get("topic", ev.get("device_id", "")) not in (VISUAL_TOPIC, DEVICE_ID):
                if kind == "accepted":
                    self.last_rx[ev["topic"]] = time.time()
                return
            if kind == "accepted":
                data = ev["data"]
                self.last_rx[ev["topic"]] = time.time()
                self.bus.publish("gateway_rx", topic=ev["topic"], forwarded_to=ev["forwarded_to"], payload=data,
                                 bytes=ev["bytes"], latency_ms=data["gateway"]["gw_latency_ms"])
            elif kind == "rejected":
                self.last_reject = (ev["topic"], ev["reason"], time.time())
                self.bus.publish("gateway_reject", topic=ev["topic"], reason=ev["reason"], size=ev["size"])
            else:  # gap / device_restart
                self.bus.publish("gateway_event", **ev)

        gw = Gateway(self.broker_ep, client_id="gateway-visualizer", on_event=on_event)
        if not gw.start(retries=2):
            raise RuntimeError("gateway could not connect to the broker")
        self.gateway = gw
        self.bus.publish("info", message=f"Gateway connected directly to broker :{self.broker_ep.port}, subscribed to "
                                         f"{TOPIC_INGEST_ALL}; validates every message and forwards good ones to "
                                         f"sensors/<id>/telemetry")

    # ------------------------------------------------------------------ device + attack connections
    def open_client(self, identity: str, label: str, own_cert: Path | None = None, **build_kwargs):
        """Connect a client THROUGH the wire tap and report what happened.

        own_cert - the certificate this client presents (mTLS), for display only.
        """
        self.tap.label_next(label)
        client = build_client(self.tap_ep, identity, client_id=f"{label}-{int(time.time() * 1000) % 100000}", **build_kwargs)
        result = connect_blocking(client, self.tap_ep, timeout=5)
        evt = {"actor": label, "identity": identity, "ok": result.ok, "connect_ms": result.connect_ms,
               "reason": result.reason, "tls_version": result.tls_version, "cipher": result.cipher}
        if result.ok and self.mode != "plain":
            sock = client.socket()
            evt["peer_cert"] = describe_cert(x509.load_der_x509_certificate(sock.getpeercert(binary_form=True)))
            evt["hostname_checked"] = self.tap_ep.host
        if self.mode == "mtls":
            crt = own_cert or client_cert_paths(identity)[0]
            if Path(crt).exists():
                evt["own_cert"] = describe_cert(x509.load_pem_x509_certificate(Path(crt).read_bytes()))
        self.bus.publish("connect", **evt)
        return client, result

    def connect_device(self) -> bool:
        if self.device_client is not None:
            try:
                self.device_client.disconnect()
                self.device_client.loop_stop()
            except Exception:  # noqa: BLE001
                pass
        client, result = self.open_client(DEVICE_ID, DEVICE_ID)
        if not result.ok:
            self.device_client = None
            return False
        self.device_client = client
        if self.device is None:
            self.device = SimulatedDevice(DEVICE_ID, client, AgriSensorModel(DEVICE_ID, seed=None), qos=1)
        else:
            self.device.client = client
        return True

    def publish_reading(self, topic_override: str | None = None) -> dict | None:
        if self.device is None or self.device_client is None:
            self.bus.publish("error", message="Device is not connected")
            return None
        # Build first and announce the plaintext BEFORE it is sent, so the UI can
        # pair it with the (encrypted) record that the wire tap sees next.
        self.device.seq += 1
        now = clock.wall()
        msg = build_message(DEVICE_ID, self.device.seq, self.device.model.read(now), ts_sent=now)
        topic = topic_override or self.device.topic
        payload = json.dumps(msg, separators=(",", ":"))
        remaining = 2 + len(topic) + 2 + len(payload)            # topic + packet id (QoS 1) + payload
        mqtt_len = 1 + (1 if remaining < 128 else 2 if remaining < 16384 else 3) + remaining
        self.bus.publish("app_publish", actor=DEVICE_ID, topic=topic, payload=msg, payload_bytes=len(payload),
                         mqtt_bytes=mqtt_len, mode=self.mode)
        msg["ts_mono_ns"] = clock.mono_ns()  # restamp right before sending so latency excludes UI work
        wire = json.dumps(msg, separators=(",", ":"))
        self.last_sent = (topic, wire)
        self.device_client.publish(topic, wire, qos=1).wait_for_publish(timeout=5)
        return msg

    def publish_raw(self, topic: str, payload: str, shown: dict | str, note: str) -> None:
        """Publish an exact payload from dev-001 (invalid-data and replay scenarios)."""
        remaining = 2 + len(topic) + 2 + len(payload)
        mqtt_len = 1 + (1 if remaining < 128 else 2 if remaining < 16384 else 3) + remaining
        self.bus.publish("app_publish", actor=DEVICE_ID, topic=topic, payload=shown, payload_bytes=len(payload),
                         mqtt_bytes=mqtt_len, mode=self.mode, note=note)
        self.device_client.publish(topic, payload, qos=1).wait_for_publish(timeout=5)

    # ------------------------------------------------------------------ fleet (analytics load)
    def set_fleet(self, enabled: bool, devices: int = 8, rate: float = 1.0, invalid_every: int = 30) -> None:
        """Start/stop extra devices dev-002..dev-(N+1). They connect DIRECTLY to the broker (not through the
        tap) so the animation stays readable; their data feeds the analytics page."""
        with self.lock:
            self._stop_fleet()
            if enabled and self.broker is not None:
                devices = max(1, min(devices, 19))
                ids = device_ids(devices + 1)[1:]
                try:
                    fleet = Fleet(self.mode, ids=ids, qos=1)
                    fleet.connect()
                except Exception as exc:  # noqa: BLE001
                    self.bus.publish("error", message=f"fleet could not start: {exc}")
                    return
                self.fleet, self.fleet_stop = fleet, threading.Event()
                self.fleet_info = {"devices": len(fleet.devices), "rate": rate, "invalid_every": invalid_every}
                threading.Thread(target=fleet.run, args=(rate, 0, invalid_every, self.fleet_stop), daemon=True).start()
                self.bus.publish("info", message=f"Fleet started: {len(fleet.devices)} devices x {rate} msg/s "
                                                 f"(about 1 in {invalid_every} messages deliberately invalid)")
        self.bus.publish("session", state="running" if self.broker else "stopped", **self.state())

    def _stop_fleet(self) -> None:
        if self.fleet is not None:
            self.fleet_stop.set()
            time.sleep(0.3)
            self.fleet.close()
            self.fleet = None
        self.fleet_info = None

    # ------------------------------------------------------------------ auto stream
    def set_streaming(self, enabled: bool, interval: float = 2.0) -> None:
        self.streaming = enabled
        if enabled and (self._stream_thread is None or not self._stream_thread.is_alive()):
            def loop():
                while self.streaming:
                    with self.lock:
                        if self.device_client is not None:
                            self.publish_reading()
                    time.sleep(max(interval, 0.5))
            self._stream_thread = threading.Thread(target=loop, daemon=True)
            self._stream_thread.start()
        self.bus.publish("session", state="running" if self.broker else "stopped", **self.state())
