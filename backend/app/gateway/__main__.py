"""Run the gateway:  .venv\\Scripts\\python -m app.gateway --mode mtls"""
import argparse
import time

from app.config import broker_endpoint
from app.gateway.gateway import Gateway
from app.logging_setup import configure


def main() -> int:
    p = argparse.ArgumentParser(description="Secure MQTT gateway: validate ingest/+ and forward to sensors/+/telemetry")
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="mtls")
    p.add_argument("--qos", type=int, choices=[0, 1, 2], default=1)
    p.add_argument("--stats-every", type=float, default=10.0, help="seconds between summary log lines")
    args = p.parse_args()
    log = configure("gateway")

    gw = Gateway(broker_endpoint(args.mode), qos=args.qos)
    gw.start()  # retries forever until the broker is reachable
    try:
        while True:
            time.sleep(args.stats_every)
            log.info("stats: %s", gw.summary())
    except KeyboardInterrupt:
        pass
    finally:
        gw.stop()
        log.info("stopped. final stats: %s", gw.summary())
    return 0


raise SystemExit(main())
