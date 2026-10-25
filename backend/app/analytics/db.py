"""SQLite persistence for readings, security/connection events, resource samples and benchmarks.

WAL mode lets the collector write while the dashboard reads.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from app.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY,
    device_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts_sent REAL NOT NULL,            -- device wall clock (display only)
    ts_received REAL NOT NULL,        -- collector wall clock
    latency_ms REAL,                  -- device -> gateway -> collector (perf_counter, same host)
    gw_latency_ms REAL,               -- device -> gateway
    temperature_c REAL, humidity_pct REAL, soil_moisture_pct REAL,
    simulated INTEGER NOT NULL,       -- 1 = values come from the simulator
    mode TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_readings_time ON readings(ts_received);
CREATE INDEX IF NOT EXISTS ix_readings_dev ON readings(device_id, ts_received);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    source TEXT NOT NULL,             -- gateway | broker_log
    event_type TEXT NOT NULL,         -- e.g. auth_failed, tls_cert_verify_failed, schema_rejected, replay_rejected
    client_id TEXT, device_id TEXT,
    detail TEXT,
    mode TEXT
);
CREATE INDEX IF NOT EXISTS ix_sec_time ON security_events(ts);

CREATE TABLE IF NOT EXISTS connection_events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    client_id TEXT, username TEXT,
    event TEXT NOT NULL,              -- connected | disconnected | rejected
    detail TEXT,
    mode TEXT
);
CREATE INDEX IF NOT EXISTS ix_conn_time ON connection_events(ts);

CREATE TABLE IF NOT EXISTS resource_samples (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    process TEXT NOT NULL,            -- broker | gateway | collector | fleet | benchmark
    pid INTEGER,
    cpu_pct REAL,                     -- % of ONE core
    rss_mb REAL,
    run_id TEXT                       -- NULL for live demo, benchmark run id otherwise
);
CREATE INDEX IF NOT EXISTS ix_res_time ON resource_samples(ts);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id TEXT PRIMARY KEY,
    started_at REAL, mode TEXT, repetition INTEGER,
    devices INTEGER, rate_hz REAL, qos INTEGER, warmup_s REAL, duration_s REAL,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS benchmark_results (
    run_id TEXT PRIMARY KEY REFERENCES benchmark_runs(run_id),
    sent INTEGER, received INTEGER, success_rate REAL, throughput_mps REAL,
    lat_median_ms REAL, lat_p95_ms REAL, lat_mean_ms REAL,
    connect_median_ms REAL, connect_p95_ms REAL,
    broker_cpu_avg REAL, broker_rss_max_mb REAL,
    gateway_cpu_avg REAL, gateway_rss_max_mb REAL,
    client_cpu_avg REAL, client_rss_max_mb REAL
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def insert_many(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    with conn:
        conn.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])


def query_df(sql: str, params: tuple = (), path: Path | str = DB_PATH) -> pd.DataFrame:
    """Read-only query helper for the dashboard (opens its own short-lived connection)."""
    if not Path(path).exists():
        return pd.DataFrame()
    uri = f"file:{Path(path).as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=10) as conn:
        return pd.read_sql_query(sql, conn, params=params)
