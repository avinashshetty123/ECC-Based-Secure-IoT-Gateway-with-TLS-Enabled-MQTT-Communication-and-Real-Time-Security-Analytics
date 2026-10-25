"""Integration tests: real broker + gateway + multi-device fleet (Phase 5).

Covers: multiple devices end-to-end over mTLS, application-level rejection of
invalid messages (security test 7), replay protection, and recovery after the
broker restarts (security test 8).
"""
import json
import time

import pytest

from app.config import LOG_DIR, ROOT, BrokerEndpoint
from app.gateway.gateway import Gateway
from app.simulator.device import build_message
from app.simulator.fleet import Fleet
from tests.conftest import BrokerProcess
from tests.helpers import Listener, publish_once

pytestmark = pytest.mark.integration


@pytest.fixture
def gateway(mtls_broker):
    gw = Gateway(mtls_broker.endpoint, client_id="gateway-test")
    assert gw.start(retries=3)
    yield gw
    gw.stop()


def test_fleet_of_five_devices_end_to_end(mtls_broker, gateway):
    sink = Listener(mtls_broker.endpoint, "collector", "sensors/+/telemetry")
    fleet = Fleet("mtls", 5, seed=42)
    try:
        assert fleet.connect() == 5
        fleet.run(rate_hz=5, duration=2.0)
        sent = sum(fleet.stats.sent.values())
        assert sink.wait_for(sent, timeout=5), f"sent {sent}, collector got {len(sink.messages)}"
        devices = {json.loads(m.payload)["device_id"] for m in sink.messages}
        assert devices == {"dev-001", "dev-002", "dev-003", "dev-004", "dev-005"}
        assert all(json.loads(m.payload)["gateway"]["validated"] for m in sink.messages)
        assert gateway.stats["rejected"] == 0
    finally:
        fleet.close()
        sink.close()


def test_invalid_message_rejected_and_reported(mtls_broker, gateway):
    events = Listener(mtls_broker.endpoint, "collector", "gateway/events")
    telemetry = Listener(mtls_broker.endpoint, "collector", "sensors/+/telemetry")
    try:
        bad = build_message("dev-003", 1, {"temperature_c": 25.0, "humidity_pct": 250.0, "soil_moisture_pct": 40.0})
        publish_once(mtls_broker.endpoint, "dev-003", "ingest/dev-003", json.dumps(bad))
        assert events.wait_for(1)
        event = json.loads(events.messages[0].payload)
        assert event["type"] == "rejected" and "humidity_pct" in event["reason"]
        assert not telemetry.wait_for(1, timeout=1.0), "invalid data must not be forwarded"
    finally:
        events.close()
        telemetry.close()


def test_replayed_message_rejected(mtls_broker, gateway):
    telemetry = Listener(mtls_broker.endpoint, "collector", "sensors/dev-004/telemetry")
    try:
        msg = json.dumps(build_message("dev-004", 1, {"temperature_c": 20.0, "humidity_pct": 50.0, "soil_moisture_pct": 30.0}))
        publish_once(mtls_broker.endpoint, "dev-004", "ingest/dev-004", msg)
        publish_once(mtls_broker.endpoint, "dev-004", "ingest/dev-004", msg)  # exact replay
        assert telemetry.wait_for(1)
        time.sleep(0.8)
        assert len(telemetry.messages) == 1, "replayed copy must be dropped"
        assert gateway.stats["rejected"] >= 1
    finally:
        telemetry.close()


def test_gateway_recovers_after_broker_restart(tmp_path):
    """Kill the broker under a running gateway, restart it, and check traffic flows again."""
    port = 18890
    conf = (ROOT / "config" / "broker_plain.conf").read_text(encoding="utf-8")
    conf = conf.replace("listener 1884 localhost", f"listener {port} localhost")
    conf = conf.replace("logs/mosquitto_plain.log", "logs/test_reconnect.log").replace("log_dest stdout", "")
    conf_file = tmp_path / "broker_reconnect.conf"
    conf_file.write_text(conf, encoding="utf-8")
    ep = BrokerEndpoint("plain", "localhost", port)

    broker = BrokerProcess(ep, str(conf_file))
    broker.start()
    gw = Gateway(ep, client_id="gateway-reconnect-test")
    try:
        assert gw.start(retries=3)
        broker.stop()                              # broker crashes
        deadline = time.time() + 5
        while gw.connected.is_set() and time.time() < deadline:
            time.sleep(0.1)
        assert not gw.connected.is_set(), "gateway should notice the disconnect"

        broker = BrokerProcess(ep, str(conf_file))
        broker.start()                             # broker comes back
        assert gw.connected.wait(40), "gateway did not reconnect"

        sink = Listener(ep, "collector", "sensors/+/telemetry")
        msg = json.dumps(build_message("dev-005", 1, {"temperature_c": 21.0, "humidity_pct": 55.0, "soil_moisture_pct": 35.0}))
        publish_once(ep, "dev-005", "ingest/dev-005", msg)
        assert sink.wait_for(1), "no telemetry after reconnect (subscription not restored?)"
        sink.close()
        assert gw.stats["disconnects"] >= 1 and gw.stats["connects"] >= 2
    finally:
        gw.stop()
        broker.stop()
        assert (LOG_DIR / "test_reconnect.log").exists()
