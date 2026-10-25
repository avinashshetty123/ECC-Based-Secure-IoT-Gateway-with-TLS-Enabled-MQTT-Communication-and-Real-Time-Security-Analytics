"""Phase 3 prototype subscriber: prints every raw device message with its latency.

  .venv\\Scripts\\python scripts\\prototype_sub.py --mode plain
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import clock  # noqa: E402
from app.config import TOPIC_INGEST_ALL, broker_endpoint  # noqa: E402
from app.mqtt.client_factory import build_client, connect_blocking  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="plain")
    p.add_argument("--identity", default="gateway", help="must have read access to ingest/+")
    args = p.parse_args()

    endpoint = broker_endpoint(args.mode)
    client = build_client(endpoint, args.identity)

    def on_connect(c, userdata, flags, rc, props):
        c.subscribe(TOPIC_INGEST_ALL, qos=1)

    def on_message(c, userdata, message):
        received_ns = clock.mono_ns()
        try:
            data = json.loads(message.payload)
            lat = clock.latency_ms(data["ts_mono_ns"], received_ns)
            print(f"{message.topic:<16} seq={data['seq']:<4} latency={lat:7.3f} ms  {data['readings']}", flush=True)
        except (ValueError, KeyError, TypeError):
            print(f"{message.topic:<16} (not a valid sensor message, {len(message.payload)} bytes)", flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    result = connect_blocking(client, endpoint)
    if not result.ok:
        print(f"Connection failed: {result.reason}", file=sys.stderr)
        return 1
    print(f"Subscribed to {TOPIC_INGEST_ALL} on {endpoint.host}:{endpoint.port} ({endpoint.mode}). Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
