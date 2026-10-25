"""Reproducible benchmark of Experiment A (plain), B (TLS) and C (mutual TLS).

  .venv\\Scripts\\python -m app.analytics.benchmark                 # uses config/benchmark.json
  .venv\\Scripts\\python -m app.analytics.benchmark --quick         # 1 repetition, short windows (smoke test)

For every (mode, repetition) a FRESH broker and gateway are started, then:
  1. Connection setup time: N sequential connects of device identities on the idle system
     (connect() -> CONNACK: TCP + TLS handshake + MQTT auth). Measured separately from latency.
  2. Load: D devices x R msg/s for warm-up + measurement window. Only messages SENT inside the
     window count. Latency = device -> broker -> gateway -> broker -> sink, using
     time.perf_counter_ns() (one shared clock on this host).
  3. CPU / RSS of broker, gateway and the client process (fleet + sink) sampled during the window.
After the repetitions, a batch of unauthorised connection attempts is made against each mode.

Output: reports/benchmarks/<timestamp>/{config.json, runs.csv, summary.csv, latencies.csv,
connect_times.csv, resources.csv, security_attempts.csv, environment.json} + SQLite rows.
All numbers are measured; nothing is estimated or hard-coded.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import ssl
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import paho.mqtt.client as mqtt
import psutil
from paho.mqtt.enums import CallbackAPIVersion

from app import clock
from app.analytics import db
from app.analytics.resources import ResourceSampler, real_process
from app.config import CERT_DIR, LOG_DIR, MOSQUITTO_DIR, ROOT, TOPIC_TELEMETRY_ALL, broker_endpoint, device_ids
from app.mqtt.client_factory import build_client, connect_blocking, tls_context
from app.simulator.fleet import Fleet
from app.winjob import kill_with_parent

OUT_ROOT = ROOT / "reports" / "benchmarks"
NEG = CERT_DIR / "negative"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ process management
class Stack:
    """A fresh broker (+ optional gateway) for one run."""

    def __init__(self, mode: str, with_gateway: bool = True):
        self.mode = mode
        self.ep = broker_endpoint(mode)
        self.with_gateway = with_gateway
        self.broker: subprocess.Popen | None = None
        self.gateway: subprocess.Popen | None = None
        self.log_path = LOG_DIR / f"bench_broker_{mode}.log"

    def __enter__(self):
        src = (ROOT / "config" / f"broker_{self.mode}.conf").read_text(encoding="utf-8")
        conf = re.sub(r"^log_dest .*$", "", src, flags=re.M) + f"\nlog_dest file logs/{self.log_path.name}\n"
        conf_path = LOG_DIR / "bench" / f"broker_{self.mode}.conf"
        conf_path.parent.mkdir(parents=True, exist_ok=True)
        conf_path.write_text(conf, encoding="utf-8")
        self.log_path.write_text("", encoding="utf-8")
        self.broker = subprocess.Popen([str(MOSQUITTO_DIR / "mosquitto.exe"), "-c", str(conf_path.relative_to(ROOT))],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=CREATE_NO_WINDOW)
        kill_with_parent(self.broker)
        self._wait_log(" running", "broker did not start")
        if self.with_gateway:
            self.gateway = subprocess.Popen([sys.executable, "-m", "app.gateway", "--mode", self.mode, "--stats-every",
                                             "3600"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=CREATE_NO_WINDOW)
            kill_with_parent(self.gateway)
            self._wait_log("u'gateway'", "gateway did not connect")
            time.sleep(0.5)  # let it subscribe
        return self

    def _wait_log(self, needle: str, err: str, timeout: float = 15) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if needle in self.log_path.read_text(encoding="utf-8", errors="replace"):
                return
            time.sleep(0.1)
        raise RuntimeError(f"{err} (see {self.log_path})")

    def __exit__(self, *exc):
        for p in (self.gateway, self.broker):
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        time.sleep(0.5)  # let Windows release the port


# ------------------------------------------------------------------ measurements
def measure_connect_times(mode: str, samples: int, devices: int) -> list[float]:
    ep = broker_endpoint(mode)
    ids = device_ids(devices)
    out = []
    for i in range(samples):
        client = build_client(ep, ids[i % len(ids)], client_id=f"conn-test-{i}")
        result = connect_blocking(client, ep, timeout=10)
        if not result.ok:
            raise RuntimeError(f"connect sample {i} failed in {mode}: {result.reason}")
        out.append(result.connect_ms)
        client.disconnect()
        client.loop_stop()
        time.sleep(0.05)
    return out


class Sink:
    """Receives validated telemetry from the gateway and records receive time per (device, seq)."""

    def __init__(self, mode: str):
        self.ep = broker_endpoint(mode)
        self.rx: dict[tuple[str, int], tuple[int, int]] = {}  # (dev, seq) -> (sent_ns, recv_ns)
        self.duplicates = 0
        self.client = build_client(self.ep, "benchmark", client_id="benchmark-sink")
        self.client.on_connect = lambda c, u, f, rc, p: c.subscribe(TOPIC_TELEMETRY_ALL, qos=1)
        self.client.on_message = self._on_message
        self.ready = threading.Event()
        self.client.on_subscribe = lambda *a: self.ready.set()

    def _on_message(self, c, u, msg):
        now = clock.mono_ns()
        d = json.loads(msg.payload)
        key = (d["device_id"], d["seq"])
        if key in self.rx:
            self.duplicates += 1  # QoS 1 = at-least-once: a duplicate delivery is possible
            return
        self.rx[key] = (d["ts_mono_ns"], now)

    def start(self):
        r = connect_blocking(self.client, self.ep)
        if not r.ok:
            raise RuntimeError(f"sink could not connect: {r.reason}")
        if not self.ready.wait(5):
            raise RuntimeError("sink subscription not acknowledged")

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()


def run_once(mode: str, rep: int, cfg: dict, run_id: str) -> tuple[dict, list, list, list]:
    with Stack(mode) as stack:
        connect_ms = measure_connect_times(mode, cfg["connect_samples"], cfg["devices"])

        sink = Sink(mode)
        sink.start()
        fleet = Fleet(mode, cfg["devices"], qos=cfg["qos"], seed=cfg["seed"] + rep)
        if fleet.connect() != cfg["devices"]:
            raise RuntimeError(f"not all devices connected: {fleet.stats.failed}")

        sent: list[tuple[str, int, int]] = []
        lock = threading.Lock()

        def on_sent(msg):
            with lock:
                sent.append((msg["device_id"], msg["seq"], msg["ts_mono_ns"]))

        # real_process(): follow the Windows venv launcher to the actual gateway interpreter
        procs = {"broker": psutil.Process(stack.broker.pid), "gateway": real_process(psutil.Process(stack.gateway.pid)),
                 "client": psutil.Process()}
        samples: list[dict] = []
        sampler = ResourceSampler(samples.extend, interval=cfg["resource_sample_interval_s"], processes=procs,
                                  run_id=run_id)

        t_start = clock.mono_ns()
        w0 = t_start + int(cfg["warmup_s"] * 1e9)
        w1 = w0 + int(cfg["duration_s"] * 1e9)
        sampler_started = threading.Event()

        def start_sampler_after_warmup():
            time.sleep(cfg["warmup_s"])
            sampler.start()
            sampler_started.set()

        threading.Thread(target=start_sampler_after_warmup, daemon=True).start()
        fleet.run(cfg["rate_hz_per_device"], cfg["warmup_s"] + cfg["duration_s"], on_sent=on_sent)
        sampler.stop()
        time.sleep(cfg["drain_s"])  # let in-flight messages arrive
        fleet.close()
        sink.stop()

    in_window = [(d, s, ns) for d, s, ns in sent if w0 <= ns < w1]
    lat_rows = []
    for d, s, ns in in_window:
        hit = sink.rx.get((d, s))
        if hit:
            lat_rows.append({"run_id": run_id, "mode": mode, "repetition": rep, "device_id": d, "seq": s,
                             "latency_ms": (hit[1] - hit[0]) / 1e6})
    lats = [r["latency_ms"] for r in lat_rows]
    res = pd.DataFrame(samples)

    def res_stat(proc, col, fn):
        sub = res[res["process"] == proc][col] if not res.empty else pd.Series(dtype=float)
        return float(fn(sub)) if len(sub) else None

    q = statistics.quantiles(lats, n=100) if len(lats) >= 2 else [float("nan")] * 99
    cq = statistics.quantiles(connect_ms, n=100) if len(connect_ms) >= 2 else [float("nan")] * 99
    summary = {
        "run_id": run_id, "mode": mode, "repetition": rep,
        "sent": len(in_window), "received": len(lats),
        "success_rate": len(lats) / len(in_window) if in_window else None,
        "throughput_mps": len(lats) / cfg["duration_s"],
        "lat_median_ms": statistics.median(lats) if lats else None, "lat_p95_ms": q[94],
        "lat_mean_ms": statistics.fmean(lats) if lats else None,
        "connect_median_ms": statistics.median(connect_ms), "connect_p95_ms": cq[94],
        "broker_cpu_avg": res_stat("broker", "cpu_pct", pd.Series.mean),
        "broker_rss_max_mb": res_stat("broker", "rss_mb", pd.Series.max),
        "gateway_cpu_avg": res_stat("gateway", "cpu_pct", pd.Series.mean),
        "gateway_rss_max_mb": res_stat("gateway", "rss_mb", pd.Series.max),
        "client_cpu_avg": res_stat("client", "cpu_pct", pd.Series.mean),
        "client_rss_max_mb": res_stat("client", "rss_mb", pd.Series.max),
        "duplicates": sink.duplicates,
    }
    conn_rows = [{"run_id": run_id, "mode": mode, "repetition": rep, "attempt": i + 1, "connect_ms": v}
                 for i, v in enumerate(connect_ms)]
    for s in samples:
        s.update({"mode": mode, "repetition": rep})
    return summary, lat_rows, conn_rows, samples


# ------------------------------------------------------------------ security attempts
def security_attempts(mode: str, n: int) -> list[dict]:
    """Unauthorised attempts that MUST be rejected. Outcome is observed, not assumed."""
    ep = broker_endpoint(mode)
    cases: list[tuple[str, callable]] = []
    if mode in ("plain", "tls"):
        cases.append(("wrong password", lambda: build_client(ep, "dev-001", password="wrong-password")))

        def anon():
            c = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
            if mode == "tls":
                c.tls_set_context(tls_context("tls", "x"))
            return c
        cases.append(("anonymous", anon))
    if mode in ("tls", "mtls"):
        cases.append(("broker not trusted by client (rogue CA trust store)",
                      lambda: build_client(ep, "dev-001", ssl_context=tls_context(mode, "dev-001", ca_file=NEG / "rogue_ca.crt"))))
    if mode == "mtls":
        for stem, label in [("rogue_client", "client cert from rogue CA"), ("expired_client", "expired client cert"),
                            ("server_as_client", "wrong-purpose (serverAuth) client cert")]:
            cases.append((label, lambda stem=stem: build_client(
                ep, "dev-001", ssl_context=tls_context("mtls", "dev-001", cert_file=NEG / f"{stem}.crt",
                                                       key_file=NEG / f"{stem}.key"))))

        def no_cert():
            c = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
            c.tls_set_context(tls_context("tls", "x"))
            return c
        cases.append(("no client certificate", no_cert))

    rows = []
    with Stack(mode, with_gateway=False) as stack:
        for label, make in cases:
            rejected = 0
            reasons = set()
            for _ in range(n):
                client = make()
                r = connect_blocking(client, ep, timeout=5)
                if r.ok:
                    client.disconnect()
                    client.loop_stop()
                else:
                    rejected += 1
                    reasons.add(r.reason.split(":")[0] if "certificate verification" in r.reason else r.reason)
            rows.append({"mode": mode, "attempt": label, "attempts": n, "rejected": rejected,
                         "accepted": n - rejected, "expected": "rejected",
                         "result": "PASS" if rejected == n else "FAIL", "client_side_reason": "; ".join(sorted(reasons))})
        time.sleep(0.5)
        broker_log = stack.log_path.read_text(encoding="utf-8", errors="replace")
    tls_errors = len(re.findall(r"OpenSSL Error", broker_log))
    auth_fail = len(re.findall(r"not authori[sz]ed", broker_log))
    for r in rows:
        r["broker_log_tls_errors_total"] = tls_errors
        r["broker_log_auth_failures_total"] = auth_fail
    return rows


# ------------------------------------------------------------------ aggregation
def summarise(runs: pd.DataFrame, lat: pd.DataFrame) -> pd.DataFrame:
    metrics = ["lat_median_ms", "lat_p95_ms", "throughput_mps", "success_rate", "connect_median_ms",
               "connect_p95_ms", "broker_cpu_avg", "broker_rss_max_mb", "gateway_cpu_avg", "client_cpu_avg"]
    rows = []
    base = None
    for mode in [m for m in ("plain", "tls", "mtls") if m in runs["mode"].unique()]:
        r = runs[runs["mode"] == mode]
        row = {"mode": mode, "experiment": {"plain": "A", "tls": "B", "mtls": "C"}[mode], "repetitions": len(r),
               "messages_measured": int(r["received"].sum())}
        for m in metrics:
            row[f"{m}_mean"] = round(r[m].mean(), 4)
            row[f"{m}_std"] = round(r[m].std(ddof=1), 4) if len(r) > 1 else None
        pooled = lat[lat["mode"] == mode]["latency_ms"]
        row["pooled_lat_median_ms"] = round(pooled.median(), 4)
        row["pooled_lat_p95_ms"] = round(pooled.quantile(0.95), 4)
        row["pooled_lat_p99_ms"] = round(pooled.quantile(0.99), 4)
        if mode == "plain":
            base = row
        elif base:
            row["lat_median_overhead_vs_plain_pct"] = round(
                100 * (row["pooled_lat_median_ms"] / base["pooled_lat_median_ms"] - 1), 1)
            row["connect_overhead_vs_plain_pct"] = round(
                100 * (row["connect_median_ms_mean"] / base["connect_median_ms_mean"] - 1), 1)
        rows.append(row)
    return pd.DataFrame(rows)


def environment() -> dict:
    mosq = subprocess.run([str(MOSQUITTO_DIR / "mosquitto.exe"), "-h"], capture_output=True, text=True)
    mv = re.search(r"mosquitto version [\d.]+", mosq.stdout + mosq.stderr)
    return {"python": platform.python_version(), "os": platform.platform(), "cpu": platform.processor(),
            "logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
            "openssl_python": ssl.OPENSSL_VERSION, "mosquitto": mv.group(0) if mv else "unknown",
            "paho_mqtt": mqtt.__version__ if hasattr(mqtt, "__version__") else "2.x"}


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark plain vs TLS vs mTLS")
    p.add_argument("--config", type=Path, default=ROOT / "config" / "benchmark.json")
    p.add_argument("--quick", action="store_true", help="1 repetition, 3 s warm-up, 8 s window (smoke test)")
    p.add_argument("--modes", nargs="*", choices=["plain", "tls", "mtls"])
    args = p.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    if args.quick:
        cfg.update(repetitions=1, warmup_s=3, duration_s=8, connect_samples=10, security_attempts_per_type=2)
    if args.modes:
        cfg["modes"] = args.modes

    for mode in cfg["modes"]:
        ep = broker_endpoint(mode)
        with __import__("socket").socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", ep.port)) == 0:
                log(f"ERROR: port {ep.port} ({mode}) is in use - stop the demo/visualizer first.")
                return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + ("-quick" if args.quick else "")
    out = OUT_ROOT / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (out / "environment.json").write_text(json.dumps(environment(), indent=2), encoding="utf-8")
    total = len(cfg["modes"]) * cfg["repetitions"]
    est = total * (cfg["warmup_s"] + cfg["duration_s"] + cfg["drain_s"] + 6) + len(cfg["modes"]) * 15
    log(f"Benchmark -> {out.relative_to(ROOT)}  ({total} runs, about {est / 60:.1f} min)")

    conn = db.connect()
    runs, lats, conns, resources = [], [], [], []
    # Interleave modes per repetition (A,B,C,A,B,C...) so slow drift of the laptop affects all equally
    for rep in range(1, cfg["repetitions"] + 1):
        for mode in cfg["modes"]:
            run_id = f"{stamp}-{mode}-r{rep}"
            log(f"run {run_id}: {cfg['devices']} devices x {cfg['rate_hz_per_device']} msg/s, "
                f"warm-up {cfg['warmup_s']} s, window {cfg['duration_s']} s")
            s, l, c, r = run_once(mode, rep, cfg, run_id)
            log(f"   sent {s['sent']}  received {s['received']}  success {s['success_rate']:.4f}  "
                f"median {s['lat_median_ms']:.3f} ms  p95 {s['lat_p95_ms']:.3f} ms  connect {s['connect_median_ms']:.2f} ms")
            runs.append(s), lats.extend(l), conns.extend(c), resources.extend(r)
            db.insert_many(conn, "benchmark_runs", [{
                "run_id": run_id, "started_at": time.time(), "mode": mode, "repetition": rep,
                "devices": cfg["devices"], "rate_hz": cfg["rate_hz_per_device"], "qos": cfg["qos"],
                "warmup_s": cfg["warmup_s"], "duration_s": cfg["duration_s"], "config_json": json.dumps(cfg)}])
            db.insert_many(conn, "benchmark_results", [{k: v for k, v in s.items()
                                                        if k not in ("mode", "repetition", "duplicates")}])
            db.insert_many(conn, "resource_samples", [{k: v for k, v in x.items() if k not in ("mode", "repetition")}
                                                      for x in r])

    sec_rows = []
    for mode in cfg["modes"]:
        log(f"security attempts against {mode}")
        sec_rows.extend(security_attempts(mode, cfg["security_attempts_per_type"]))

    runs_df, lat_df = pd.DataFrame(runs), pd.DataFrame(lats)
    runs_df.to_csv(out / "runs.csv", index=False)
    lat_df.to_csv(out / "latencies.csv", index=False)
    pd.DataFrame(conns).to_csv(out / "connect_times.csv", index=False)
    pd.DataFrame(resources).to_csv(out / "resources.csv", index=False)
    pd.DataFrame(sec_rows).to_csv(out / "security_attempts.csv", index=False)
    summary = summarise(runs_df, lat_df)
    summary.to_csv(out / "summary.csv", index=False)

    log("Summary (pooled over repetitions):")
    cols = ["experiment", "mode", "messages_measured", "pooled_lat_median_ms", "pooled_lat_p95_ms",
            "throughput_mps_mean", "success_rate_mean", "connect_median_ms_mean", "broker_cpu_avg_mean"]
    print(summary[cols].to_string(index=False), flush=True)
    failed = [r for r in sec_rows if r["result"] != "PASS"]
    log(f"Security attempts: {len(sec_rows) - len(failed)}/{len(sec_rows)} attack types fully rejected")
    log(f"Results written to {out.relative_to(ROOT)}")
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
