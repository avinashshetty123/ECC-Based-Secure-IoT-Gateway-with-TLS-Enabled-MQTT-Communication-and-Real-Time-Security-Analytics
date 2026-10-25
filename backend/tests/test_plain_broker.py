"""Integration tests against a real Mosquitto broker in PLAIN mode (Experiment A config).

Covers security-test plan items 1, 4, 5, 6 for the baseline listener.
"""
import json

import pytest

from app.config import broker_endpoint
from app.mqtt.client_factory import build_client, connect_blocking
from app.simulator.device import build_message
from tests.helpers import Listener, publish_once

pytestmark = pytest.mark.integration
READINGS = {"temperature_c": 25.0, "humidity_pct": 60.0, "soil_moisture_pct": 40.0}


def test_valid_device_message_reaches_gateway(plain_broker):
    ep = plain_broker.endpoint
    listener = Listener(ep, "gateway", "ingest/+")
    try:
        payload = json.dumps(build_message("dev-001", 1, READINGS))
        publish_once(ep, "dev-001", "ingest/dev-001", payload)
        assert listener.wait_for(1)
        assert json.loads(listener.messages[0].payload)["device_id"] == "dev-001"
    finally:
        listener.close()


def test_wrong_password_is_rejected(plain_broker):
    client = build_client(plain_broker.endpoint, "dev-001", password="definitely-wrong")
    result = connect_blocking(client, plain_broker.endpoint, timeout=5)
    assert not result.ok
    assert "not authori" in result.reason.lower()


def test_unknown_user_is_rejected(plain_broker):
    client = build_client(plain_broker.endpoint, "intruder", password="x")
    assert not connect_blocking(client, plain_broker.endpoint, timeout=5).ok


def test_anonymous_is_rejected(plain_broker):
    import paho.mqtt.client as mqtt
    from paho.mqtt.enums import CallbackAPIVersion

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    assert not connect_blocking(client, plain_broker.endpoint, timeout=5).ok


def test_device_cannot_impersonate_another_device(plain_broker):
    """ACL: dev-001 may only write ingest/dev-001. A publish to ingest/dev-002 is dropped."""
    ep = plain_broker.endpoint
    listener = Listener(ep, "gateway", "ingest/+")
    try:
        publish_once(ep, "dev-001", "ingest/dev-002", json.dumps(build_message("dev-002", 1, READINGS)))
        assert not listener.wait_for(1, timeout=1.5)
    finally:
        listener.close()


def test_device_cannot_publish_fake_validated_telemetry(plain_broker):
    """ACL: only the gateway may write sensors/+/telemetry."""
    ep = plain_broker.endpoint
    listener = Listener(ep, "collector", "sensors/+/telemetry")
    try:
        publish_once(ep, "dev-001", "sensors/dev-001/telemetry", json.dumps(build_message("dev-001", 1, READINGS)))
        assert not listener.wait_for(1, timeout=1.5)
    finally:
        listener.close()


@pytest.mark.parametrize("topic", ["ingest/+", "ingest/dev-002", "sensors/+/telemetry", "#"])
def test_device_cannot_read_other_data(plain_broker, topic):
    """ACL: devices have no read rights.

    Observed Mosquitto 2.1.2 behaviour: the SUBSCRIBE itself is acknowledged
    ("Granted QoS 1"), but the read ACL is checked for every message, so
    nothing is ever delivered. The security property we test is therefore
    "no data reaches the unauthorised subscriber", not the SUBACK code.
    """
    ep = plain_broker.endpoint
    spy = Listener(ep, "dev-001", topic)
    try:
        publish_once(ep, "dev-002", "ingest/dev-002", json.dumps(build_message("dev-002", 1, READINGS)))
        assert not spy.wait_for(1, timeout=1.5), f"dev-001 received data via {topic}"
    finally:
        spy.close()
