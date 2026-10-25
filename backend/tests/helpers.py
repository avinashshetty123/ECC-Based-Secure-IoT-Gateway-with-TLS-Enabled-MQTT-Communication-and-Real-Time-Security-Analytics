"""Small MQTT helpers shared by the integration tests."""
from __future__ import annotations

import threading
import time

import paho.mqtt.client as mqtt

from app.config import BrokerEndpoint
from app.mqtt.client_factory import build_client, connect_blocking


class Listener:
    """Connect as `identity`, subscribe to `topic`, and record messages + SUBACK codes."""

    def __init__(self, endpoint: BrokerEndpoint, identity: str, topic: str, **build_kwargs):
        self.messages: list[mqtt.MQTTMessage] = []
        self.suback_codes: list = []
        self._subscribed = threading.Event()
        self.client = build_client(endpoint, identity, **build_kwargs)
        self.client.on_message = lambda c, u, m: self.messages.append(m)

        def on_subscribe(c, u, mid, reason_codes, props):
            self.suback_codes = list(reason_codes)
            self._subscribed.set()

        self.client.on_subscribe = on_subscribe
        self.result = connect_blocking(self.client, endpoint)
        assert self.result.ok, f"listener {identity} failed to connect: {self.result.reason}"
        self.client.subscribe(topic, qos=1)
        assert self._subscribed.wait(5), "no SUBACK received"

    def wait_for(self, n: int, timeout: float = 3.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if len(self.messages) >= n:
                return True
            time.sleep(0.05)
        return len(self.messages) >= n

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def publish_once(endpoint: BrokerEndpoint, identity: str, topic: str, payload: str, **build_kwargs) -> None:
    client = build_client(endpoint, identity, **build_kwargs)
    result = connect_blocking(client, endpoint)
    assert result.ok, f"publisher {identity} failed to connect: {result.reason}"
    client.publish(topic, payload, qos=1).wait_for_publish(timeout=5)
    client.disconnect()
    client.loop_stop()
