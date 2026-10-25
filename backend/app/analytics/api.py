"""JSON-ready analytics for the frontend (computed from SQLite and benchmark CSVs).

Every number returned here is derived from stored measurements; nothing is estimated.
"""
from __future__ import annotations

import json
import math
import time

import pandas as pd

from app.analytics.db import query_df
from app.config import ROOT

BENCH_DIR = ROOT / "reports" / "benchmarks"


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def _since(window: float | None) -> float:
    return 0.0 if window is None else time.time() - window


def overview(window: float | None) -> dict:
    since = _since(window)
    r = query_df("SELECT ts_received, device_id, latency_ms FROM readings WHERE ts_received >= ?", (since,))
    sec = query_df("SELECT ts, source, event_type, device_id, client_id, detail FROM security_events "
                   "WHERE ts >= ? ORDER BY ts DESC", (since,))
    conn = query_df("SELECT event, COUNT(*) AS n FROM connection_events WHERE ts >= ? GROUP BY event", (since,))
    res = query_df("SELECT ts, process, cpu_pct, rss_mb FROM resource_samples WHERE run_id IS NULL AND ts >= ? "
                   "ORDER BY ts", (max(since, time.time() - 600),))
    now = time.time()
    out: dict = {"generated_at": now, "window_s": window}

    if r.empty:
        out["kpi"] = {"messages": 0, "msgs_per_s": 0, "devices_active": 0, "lat_median_ms": None, "lat_p95_ms": None}
        out["series"] = []
        out["histogram"] = []
    else:
        recent = r[r["ts_received"] >= now - 30]
        out["kpi"] = {"messages": len(r), "msgs_per_s": round(len(recent) / 30, 2),
                      "devices_active": int(recent["device_id"].nunique()),
                      "lat_median_ms": round(float(r["latency_ms"].median()), 3),
                      "lat_p95_ms": round(float(r["latency_ms"].quantile(0.95)), 3)}
        r["bucket"] = (r["ts_received"] // 5 * 5).astype(int)
        g = r.groupby("bucket")["latency_ms"]
        series = pd.DataFrame({"t": g.size().index, "msgs_per_s": g.size().values / 5,
                               "median_ms": g.median().values, "p95_ms": g.quantile(0.95).values}).tail(120)
        out["series"] = _records(series.round(3))
        p99 = r["latency_ms"].quantile(0.99)
        counts = pd.cut(r.loc[r["latency_ms"] <= p99, "latency_ms"], bins=30).value_counts(sort=False)
        out["histogram"] = [{"from": round(iv.left, 3), "to": round(iv.right, 3), "count": int(c)}
                            for iv, c in counts.items()]
        out["kpi"]["lat_p99_ms"] = round(float(p99), 3)

    gw = sec[sec["source"] == "gateway"] if not sec.empty else sec
    out["kpi"]["rejected_messages"] = int(gw["event_type"].isin(["schema_rejected", "replay_rejected"]).sum()) if not sec.empty else 0
    out["kpi"]["connection_blocks"] = int((sec["source"] == "broker_log").sum()) if not sec.empty else 0
    out["security_counts"] = (sec["event_type"].value_counts().rename_axis("type").reset_index(name="count")
                              .to_dict("records") if not sec.empty else [])
    out["security_recent"] = _records(sec.head(60)) if not sec.empty else []
    out["connections"] = conn.to_dict("records") if not conn.empty else []
    if res.empty:
        out["resources"] = []
    else:
        res["t"] = (res["ts"] // 2 * 2).astype(int)
        out["resources"] = _records(res.groupby(["t", "process"], as_index=False)[["cpu_pct", "rss_mb"]].mean().round(2))
    return out


def sensors(window: float | None, devices: list[str]) -> dict:
    since = _since(window)
    all_dev = query_df("SELECT DISTINCT device_id FROM readings WHERE ts_received >= ? ORDER BY device_id", (since,))
    device_list = all_dev["device_id"].tolist() if not all_dev.empty else []
    chosen = [d for d in devices if d in device_list] or device_list[:4]
    if not chosen:
        return {"devices": device_list, "selected": [], "series": {}, "latest": []}
    marks = ",".join("?" for _ in chosen)
    df = query_df(f"SELECT device_id, seq, ts_received, temperature_c, humidity_pct, soil_moisture_pct FROM readings "
                  f"WHERE ts_received >= ? AND device_id IN ({marks}) ORDER BY ts_received", (since, *chosen))
    series = {}
    for dev, sub in df.groupby("device_id"):
        sub = sub.iloc[:: max(len(sub) // 300, 1)]  # at most ~300 points per device
        series[dev] = _records(sub[["ts_received", "temperature_c", "humidity_pct", "soil_moisture_pct"]].round(2))
    latest = df.sort_values("ts_received").groupby("device_id").tail(1)
    return {"devices": device_list, "selected": chosen, "series": series, "latest": _records(latest.round(2))}


EXPORTABLE = {
    "readings": "ts_received",
    "security_events": "ts",
    "connection_events": "ts",
    "resource_samples": "ts",
}


def export_csv(table: str, window: float | None) -> str | None:
    """CSV of one table for the selected time window (None if the table is not exportable)."""
    if table not in EXPORTABLE:
        return None
    df = query_df(f"SELECT * FROM {table} WHERE {EXPORTABLE[table]} >= ? ORDER BY {EXPORTABLE[table]}", (_since(window),))
    return df.to_csv(index=False)


def benchmark_runs() -> list[dict]:
    if not BENCH_DIR.exists():
        return []
    return [{"id": d.name, "has_summary": (d / "summary.csv").exists()}
            for d in sorted(BENCH_DIR.iterdir(), reverse=True) if d.is_dir() and (d / "summary.csv").exists()]


def benchmark(run_id: str) -> dict | None:
    runs = benchmark_runs()
    if not runs:
        return None
    rid = runs[0]["id"] if run_id == "latest" else run_id
    d = BENCH_DIR / rid
    if not (d / "summary.csv").exists() or d.parent != BENCH_DIR:
        return None
    out = {"id": rid,
           "summary": _records(pd.read_csv(d / "summary.csv")),
           "runs": _records(pd.read_csv(d / "runs.csv")),
           "config": json.loads((d / "config.json").read_text(encoding="utf-8")),
           "environment": json.loads((d / "environment.json").read_text(encoding="utf-8"))
           if (d / "environment.json").exists() else {}}
    sec = d / "security_attempts.csv"
    out["security"] = _records(pd.read_csv(sec)) if sec.exists() else []
    lat_file = d / "latencies.csv"
    out["cdf"] = {}
    if lat_file.exists():
        lat = pd.read_csv(lat_file)
        for mode, sub in lat.groupby("mode"):
            qs = [i / 100 for i in range(0, 101, 2)]
            out["cdf"][mode] = [{"q": q, "ms": round(float(sub["latency_ms"].quantile(q)), 3)} for q in qs]
    return out
