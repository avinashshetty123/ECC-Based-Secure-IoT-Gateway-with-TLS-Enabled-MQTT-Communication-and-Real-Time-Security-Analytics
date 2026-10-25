"""Start the whole system with one command and stop it with Ctrl+C.

  .venv\\Scripts\\python -m app.run_demo --mode mtls --devices 10 --rate 1

Starts, in order: Mosquitto broker -> gateway -> collector -> device fleet -> Streamlit dashboard.
Each component writes its own log in logs/. The broker uses a copy of the real config
with 'debug' logging added, so ACL denials appear in the dashboard's security view.
"""
from __future__ import annotations

import argparse
import re
import socket
import subprocess
import sys
import time
import webbrowser

from app.config import LOG_DIR, MOSQUITTO_DIR, ROOT, broker_endpoint
from app.winjob import kill_with_parent

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["plain", "tls", "mtls"], default="mtls")
    p.add_argument("--devices", type=int, default=10)
    p.add_argument("--rate", type=float, default=1.0, help="messages/s per device")
    p.add_argument("--invalid-every", type=int, default=25, help="every Nth message is deliberately invalid (0 = off)")
    p.add_argument("--no-dashboard", action="store_true")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--duration", type=float, default=0, help="stop automatically after N seconds (0 = run until Ctrl+C)")
    args = p.parse_args()

    ep = broker_endpoint(args.mode)
    if port_open(ep.port):
        print(f"ERROR: port {ep.port} is already in use (visualizer or another broker running?). Stop it first.")
        return 1
    if not args.no_dashboard and port_open(8501):
        print("ERROR: port 8501 is already in use (dashboard already running?).")
        return 1

    # Broker config: the real one + debug log type, separate log file
    LOG_DIR.mkdir(exist_ok=True)
    src = (ROOT / "config" / f"broker_{args.mode}.conf").read_text(encoding="utf-8")
    broker_log = LOG_DIR / f"demo_broker_{args.mode}.log"
    conf = re.sub(r"^log_dest .*$", "", src, flags=re.M) + f"\nlog_dest file logs/{broker_log.name}\nlog_type debug\n"
    conf_path = LOG_DIR / "demo" / f"broker_{args.mode}.conf"
    conf_path.parent.mkdir(exist_ok=True)
    conf_path.write_text(conf, encoding="utf-8")
    broker_log.write_text("", encoding="utf-8")

    py = sys.executable
    procs: list[tuple[str, subprocess.Popen]] = []

    def launch(name: str, cmd: list[str]) -> subprocess.Popen:
        out = open(LOG_DIR / f"demo_{name}.out", "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
        kill_with_parent(proc)  # closing this window stops the children too
        procs.append((name, proc))
        print(f"  started {name:<10} pid {proc.pid}")
        return proc

    print(f"Starting the {args.mode.upper()} system ({args.devices} devices x {args.rate} msg/s)...")
    try:
        launch("broker", [str(MOSQUITTO_DIR / "mosquitto.exe"), "-c", str(conf_path.relative_to(ROOT))])
        for _ in range(80):
            if " running" in broker_log.read_text(encoding="utf-8", errors="replace"):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"broker did not start - see {broker_log}")
        launch("gateway", [py, "-m", "app.gateway", "--mode", args.mode])
        launch("collector", [py, "-m", "app.analytics.collector", "--mode", args.mode, "--broker-log", str(broker_log)])
        time.sleep(2)
        launch("fleet", [py, "-m", "app.simulator.fleet", "--mode", args.mode, "--devices", str(args.devices),
                         "--rate", str(args.rate), "--invalid-every", str(args.invalid_every)])
        if not args.no_dashboard:
            launch("dashboard", [py, "-m", "streamlit", "run", "app/dashboard/streamlit_app.py",
                                 "--server.address", "127.0.0.1", "--server.port", "8501", "--server.headless", "true",
                                 "--browser.gatherUsageStats", "false"])
            if not args.no_browser:
                time.sleep(4)
                webbrowser.open("http://127.0.0.1:8501")
            print("\n  Dashboard: http://127.0.0.1:8501")
        print("  Logs:      logs/demo_*.out, logs/gateway.log, logs/collector.log, logs/" + broker_log.name)
        print("  Press Ctrl+C to stop everything.\n")
        end = time.time() + args.duration if args.duration else float("inf")
        while time.time() < end:
            time.sleep(2)
            for name, proc in procs:
                if proc.poll() is not None:
                    raise RuntimeError(f"{name} exited with code {proc.returncode} - see logs/demo_{name}.out")
    except KeyboardInterrupt:
        print("\nStopping...")
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        return 1
    finally:
        for name, proc in reversed(procs):  # devices first, broker last
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("All components stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
