"""Triggerable demo scenarios. Every verdict is decided by what ACTUALLY happened.

expect = "delivered" | "blocked". The UI shows a PASS when the observed outcome
matches the expected one, and a FAIL otherwise. Results are never faked.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from app.config import CERT_DIR
from app.mqtt.client_factory import connect_blocking, tls_context
from app.simulator.device import build_message
from app.visualizer.session import DemoSession

NEG = CERT_DIR / "negative"


@dataclass(frozen=True)
class Scenario:
    name: str
    title: str
    description: str
    modes: tuple[str, ...]
    expect: str  # delivered | blocked
    category: str = "attack"  # normal | attack


SCENARIOS = [
    Scenario("send_reading", "Send sensor reading",
             "dev-001 publishes one JSON reading. Watch it leave as plaintext, cross the wire, and arrive at the gateway.",
             ("plain", "tls", "mtls"), "delivered", "normal"),
    Scenario("reconnect", "Reconnect device (replay handshake)",
             "dev-001 drops and re-opens its connection, so you can watch the full TLS handshake again.",
             ("plain", "tls", "mtls"), "delivered", "normal"),
    Scenario("wrong_password", "Wrong password",
             "A client claims to be dev-001 but uses the wrong password.",
             ("plain", "tls"), "blocked"),
    Scenario("anonymous", "Anonymous client",
             "A client connects with no username or password at all.",
             ("plain", "tls"), "blocked"),
    Scenario("no_client_cert", "No client certificate",
             "A client completes server verification but presents no certificate of its own.",
             ("mtls",), "blocked"),
    Scenario("rogue_cert", "Certificate from a rogue CA",
             "An attacker made their own CA and issued a certificate claiming CN=dev-001.",
             ("mtls",), "blocked"),
    Scenario("expired_cert", "Expired certificate",
             "A genuine certificate for dev-001 from OUR CA, but it expired in 2021.",
             ("mtls",), "blocked"),
    Scenario("wrong_purpose_cert", "Wrong-purpose certificate",
             "OUR CA signed it for CN=dev-001, but for TLS *server* use. It is not valid as a client identity.",
             ("mtls",), "blocked"),
    Scenario("untrusted_broker", "Impostor broker",
             "The device trusts only a different CA, as if it were talking to an impostor broker. "
             "The DEVICE must refuse the broker's certificate (server authentication).",
             ("tls", "mtls"), "blocked"),
    Scenario("impersonate", "Impersonate dev-002",
             "Authenticated dev-001 publishes a reading to dev-002's topic. The broker ACL must drop it.",
             ("plain", "tls", "mtls"), "blocked"),
    Scenario("invalid_reading", "Invalid reading (humidity 250%)",
             "dev-001 sends a correctly formatted message on its OWN topic, but with an impossible value. TLS and the ACL "
             "allow it, so the GATEWAY's schema/range validation must reject it.",
             ("plain", "tls", "mtls"), "blocked"),
    Scenario("replay", "Replay a captured message",
             "Re-send the exact bytes of dev-001's last reading (same seq). The gateway's sequence check must drop the copy.",
             ("plain", "tls", "mtls"), "blocked"),
]
BY_NAME = {s.name: s for s in SCENARIOS}


def _verdict(session: DemoSession, sc: Scenario, outcome: str, detail: str) -> None:
    session.bus.publish("verdict", name=sc.name, title=sc.title, expect=sc.expect, outcome=outcome,
                        passed=outcome == sc.expect, detail=detail, mode=session.mode)


def _attempt(session: DemoSession, sc: Scenario, identity: str, label: str, **kwargs) -> None:
    """Try to connect; delivered = connection accepted, blocked = refused."""
    client, result = session.open_client(identity, label, **kwargs)
    if result.ok:
        client.disconnect()
        client.loop_stop()
        _verdict(session, sc, "delivered", f"Connection was ACCEPTED ({result.tls_version or 'plain'})")
    else:
        _verdict(session, sc, "blocked", result.reason)


def run(session: DemoSession, name: str) -> None:
    sc = BY_NAME.get(name)
    if sc is None:
        session.bus.publish("error", message=f"Unknown scenario {name!r}")
        return
    if session.mode not in sc.modes:
        session.bus.publish("error", message=f"'{sc.title}' does not apply in {session.mode} mode "
                                             f"(available in: {', '.join(sc.modes)})")
        return
    if session.tap is None:
        session.bus.publish("error", message="Start the broker first")
        return

    with session.lock:
        session.bus.publish("scenario", name=sc.name, title=sc.title, description=sc.description,
                            expect=sc.expect, category=sc.category, mode=session.mode)
        mode = session.mode

        if name == "send_reading":
            topic = "ingest/dev-001"
            before = session.last_rx.get(topic, 0)
            if session.device_client is None and not session.connect_device():
                _verdict(session, sc, "blocked", "device could not connect")
                return
            session.publish_reading()
            _wait_rx(session, topic, before, sc)

        elif name == "reconnect":
            ok = session.connect_device()
            _verdict(session, sc, "delivered" if ok else "blocked", "device reconnected" if ok else "reconnect failed")

        elif name == "wrong_password":
            _attempt(session, sc, "dev-001", "attacker (wrong password)", password="not-the-real-password")

        elif name == "anonymous":
            session.tap.label_next("attacker (anonymous)")
            client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="anon", protocol=mqtt.MQTTv311)
            if mode == "tls":
                client.tls_set_context(tls_context("tls", "anon"))
            result = connect_blocking(client, session.tap_ep, timeout=5)
            session.bus.publish("connect", actor="attacker (anonymous)", identity="(none)", ok=result.ok,
                                connect_ms=result.connect_ms, reason=result.reason, tls_version=result.tls_version)
            if result.ok:
                client.disconnect()
                client.loop_stop()
            _verdict(session, sc, "delivered" if result.ok else "blocked", result.reason)

        elif name == "no_client_cert":
            ctx = tls_context("tls", "dev-001")  # verifies the broker, but loads NO client certificate
            _attempt(session, sc, "dev-001", "attacker (no cert)", ssl_context=ctx, own_cert=NEG / "missing.crt")

        elif name in ("rogue_cert", "expired_cert", "wrong_purpose_cert"):
            stem = {"rogue_cert": "rogue_client", "expired_cert": "expired_client",
                    "wrong_purpose_cert": "server_as_client"}[name]
            ctx = tls_context("mtls", "dev-001", cert_file=NEG / f"{stem}.crt", key_file=NEG / f"{stem}.key")
            _attempt(session, sc, "dev-001", f"attacker ({sc.title.lower()})", ssl_context=ctx, own_cert=NEG / f"{stem}.crt")

        elif name == "untrusted_broker":
            ctx = tls_context(mode, "dev-001", ca_file=NEG / "rogue_ca.crt")
            _attempt(session, sc, "dev-001", "dev-001 (wrong trust anchor)", ssl_context=ctx)

        elif name == "impersonate":
            topic = "ingest/dev-002"
            before = session.last_rx.get(topic, 0)
            if session.device_client is None:
                _verdict(session, sc, "blocked", "device not connected")
                return
            msg = build_message("dev-002", 1, {"temperature_c": 99.0, "humidity_pct": 1.0, "soil_moisture_pct": 1.0})
            payload = json.dumps(msg, separators=(",", ":"))
            remaining = 2 + len(topic) + 2 + len(payload)
            session.bus.publish("app_publish", actor="dev-001", topic=topic, payload=msg, payload_bytes=len(payload),
                                mqtt_bytes=1 + (1 if remaining < 128 else 2) + remaining, mode=mode, spoofed=True)
            session.device_client.publish(topic, payload, qos=1).wait_for_publish(timeout=5)
            _wait_rx(session, topic, before, sc,
                     blocked_detail="Broker ACL dropped it - the gateway received nothing. (MQTT 3.1.1 still sends "
                                    "PUBACK, so the attacker cannot even tell it failed.)")

        elif name in ("invalid_reading", "replay"):
            topic = "ingest/dev-001"
            before = session.last_rx.get(topic, 0)
            if session.device_client is None or session.device is None:
                _verdict(session, sc, "blocked", "device not connected")
                return
            sent_at = time.time()
            if name == "invalid_reading":
                msg = build_message("dev-001", session.device.seq + 1,
                                    {"temperature_c": 24.0, "humidity_pct": 250.0, "soil_moisture_pct": 40.0})
                payload = json.dumps(msg, separators=(",", ":"))
                session.publish_raw(topic, payload, msg, "humidity 250% is physically impossible")
            else:
                if session.last_sent is None:
                    session.publish_reading()  # need one genuine message to capture first
                    time.sleep(0.5)
                    before = session.last_rx.get(topic, 0)
                    sent_at = time.time()
                topic, payload = session.last_sent
                session.publish_raw(topic, payload, json.loads(payload), "exact copy of the previous message")
            _wait_rx(session, topic, before, sc, since=sent_at)


def _wait_rx(session: DemoSession, topic: str, before: float, sc: Scenario, timeout: float = 2.0,
             blocked_detail: str = "gateway received nothing within 2 s", since: float | None = None) -> None:
    # `since` is taken BEFORE publishing: the gateway can reject faster than we get here
    started = since if since is not None else time.time()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if session.last_rx.get(topic, 0) > before:
            _verdict(session, sc, "delivered", f"gateway accepted the message on {topic}")
            return
        rej = session.last_reject
        if rej and rej[0] == topic and rej[2] >= started:
            _verdict(session, sc, "blocked", f"gateway REJECTED it: {rej[1]}")
            return
        time.sleep(0.05)
    _verdict(session, sc, "blocked", blocked_detail)


def catalog() -> list[dict]:
    return [s.__dict__ for s in SCENARIOS]
