"""Shared pytest fixtures: start a real, isolated Mosquitto broker per mode."""
from __future__ import annotations

import socket
import subprocess
import time

import pytest

from app.config import CERT_DIR, MOSQUITTO_DIR, ROOT, SECRETS_FILE, BrokerEndpoint, broker_endpoint


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


class BrokerProcess:
    def __init__(self, endpoint: BrokerEndpoint, conf: str):
        self.endpoint = endpoint
        self.mode = endpoint.mode
        self.conf = conf
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        if _port_open(self.endpoint.port):
            pytest.fail(f"Port {self.endpoint.port} already in use - stop any running broker first.")
        exe = MOSQUITTO_DIR / "mosquitto.exe"
        if not exe.exists():
            pytest.skip(f"Mosquitto not installed at {exe}")
        if not SECRETS_FILE.exists():
            pytest.skip("Credentials not generated - run scripts/setup_credentials.py")
        if self.mode != "plain" and not (CERT_DIR / "server" / "server.crt").exists():
            pytest.skip("Certificates not generated - run scripts/gen_certs.ps1")
        self.proc = subprocess.Popen(
            [str(exe), "-c", self.conf], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            if self.proc.poll() is not None:
                pytest.fail(f"Mosquitto ({self.conf}) exited with code {self.proc.returncode}; see logs/")
            if _port_open(self.endpoint.port):
                return
            time.sleep(0.1)
        pytest.fail(f"Mosquitto ({self.conf}) did not open port {self.endpoint.port}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)


def _broker(endpoint: BrokerEndpoint, conf: str):
    b = BrokerProcess(endpoint, conf)
    b.start()
    yield b
    b.stop()


@pytest.fixture(scope="session")
def plain_broker():
    yield from _broker(broker_endpoint("plain"), "config/broker_plain.conf")


@pytest.fixture(scope="session")
def tls_broker():
    yield from _broker(broker_endpoint("tls"), "config/broker_tls.conf")


@pytest.fixture(scope="session")
def mtls_broker():
    yield from _broker(broker_endpoint("mtls"), "config/broker_mtls.conf")


@pytest.fixture(scope="session")
def wronghost_broker():
    """TLS broker whose (CA-signed) certificate is for 'wrong.example', not localhost."""
    yield from _broker(BrokerEndpoint("tls", "localhost", 8885), "config/test/broker_wronghost.conf")
