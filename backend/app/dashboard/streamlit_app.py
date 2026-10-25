"""Streamlit dashboard: sensor data, measured performance, security events, benchmark results.

  .venv\\Scripts\\python -m streamlit run app/dashboard/streamlit_app.py --server.address 127.0.0.1

Reads ONLY data/iot_gateway.db and reports/benchmarks/. It never reads keys,
certificates or credentials.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from app.analytics.db import query_df  # noqa: E402
from app.config import DB_PATH  # noqa: E402

BENCH_DIR = ROOT / "reports" / "benchmarks"
MODE_COLORS = {"plain": "#f59e0b", "tls": "#10b981", "mtls": "#3b82f6"}
SECURITY_LABELS = {  # short labels so charts stay readable; details are in the table
    "auth_failed": "Login refused",
    "tls_cert_verify_failed": "Bad client cert",
    "tls_no_client_cert": "No client cert",
    "tls_client_rejected_broker_cert": "Client refused broker cert",
    "tls_protocol_mismatch": "Non-TLS on TLS port",
    "tls_error": "Other TLS error",
    "acl_denied_publish": "ACL: publish denied",
    "schema_rejected": "Invalid message",
    "replay_rejected": "Replayed message",
    "sequence_gap": "Sequence gap",
    "device_restart": "Device restart",
}

st.set_page_config(page_title="IoT Gateway Analytics", page_icon="🔐", layout="wide")


def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color}22;color:{color};border:1px solid {color}66;padding:1px 8px;"
            f"border-radius:999px;font-size:0.75rem;font-weight:600'>{text}</span>")


SIM = badge("SIMULATED sensor values", "#a78bfa")
MEAS = badge("MEASURED on this machine", "#10b981")

# ---------------------------------------------------------------- sidebar
st.sidebar.title("🔐 IoT Gateway")
st.sidebar.caption("ECC + TLS MQTT gateway · analytics")
window_label = st.sidebar.selectbox("Time range", ["Last 5 minutes", "Last 15 minutes", "Last hour", "Last 24 hours", "All data"])
WINDOW = {"Last 5 minutes": 300, "Last 15 minutes": 900, "Last hour": 3600, "Last 24 hours": 86400, "All data": None}[window_label]
auto = st.sidebar.toggle("Auto-refresh every 5 s", value=True)
devices_all = query_df("SELECT DISTINCT device_id FROM readings ORDER BY device_id")
device_options = devices_all["device_id"].tolist() if not devices_all.empty else []
selected_devices = st.sidebar.multiselect("Devices", device_options, default=device_options[:5])
st.sidebar.divider()
st.sidebar.caption(f"Database: `{DB_PATH.relative_to(ROOT)}`")
st.sidebar.caption("Start the live system with `python -m app.run_demo`. Run benchmarks with `scripts\\run_benchmarks.ps1`.")


def since() -> float:
    return 0 if WINDOW is None else time.time() - WINDOW


LOCAL_TZ = datetime.now().astimezone().tzinfo


def local_time(ts: pd.Series) -> pd.Series:
    """Unix seconds -> naive local datetimes (for chart axes)."""
    return pd.to_datetime(ts, unit="s", utc=True).dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


def load_readings() -> pd.DataFrame:
    df = query_df("SELECT * FROM readings WHERE ts_received >= ? ORDER BY ts_received", (since(),))
    if not df.empty:
        df["time"] = local_time(df["ts_received"])
    return df


st.title("ECC + TLS MQTT Gateway: real-time analytics")
st.markdown(f"Sensor values are {SIM}. Latency, throughput, CPU/RAM and security events are {MEAS}.",
            unsafe_allow_html=True)


def live_body():
    readings = load_readings()
    sec = query_df("SELECT * FROM security_events WHERE ts >= ? ORDER BY ts", (since(),))
    conns = query_df("SELECT * FROM connection_events WHERE ts >= ? ORDER BY ts", (since(),))
    res = query_df("SELECT * FROM resource_samples WHERE run_id IS NULL AND ts >= ? ORDER BY ts", (since(),))

    # ------------------------------------------------------------ KPIs
    now = time.time()
    recent = readings[readings["ts_received"] >= now - 30] if not readings.empty else readings
    k = st.columns(7)
    k[0].metric("Messages stored", f"{len(readings):,}")
    k[1].metric("Msg/s (last 30 s)", f"{len(recent) / 30:.1f}" if not readings.empty else "0")
    k[2].metric("Devices active (30 s)", recent["device_id"].nunique() if not recent.empty else 0)
    k[3].metric("Median latency", f"{readings['latency_ms'].median():.2f} ms" if not readings.empty else "-")
    k[4].metric("p95 latency", f"{readings['latency_ms'].quantile(0.95):.2f} ms" if not readings.empty else "-")
    gw_rej = int(sec["event_type"].isin(["schema_rejected", "replay_rejected"]).sum()) if not sec.empty else 0
    k[5].metric("Messages rejected", gw_rej)
    auth = int(sec["source"].eq("broker_log").sum()) if not sec.empty else 0
    k[6].metric("Connection/ACL blocks", auth)
    if readings.empty:
        st.info("No readings in this time range yet. Start the system with `.venv\\Scripts\\python -m app.run_demo` "
                "and the charts will fill in.")

    tab_sensor, tab_perf, tab_sec, tab_export = st.tabs(
        ["🌱 Sensor data", "⚡ Performance", "🛡️ Security", "⬇️ Export"])

    # ------------------------------------------------------------ sensors
    with tab_sensor:
        st.markdown(f"Readings per device, after gateway validation. {SIM}", unsafe_allow_html=True)
        view = readings[readings["device_id"].isin(selected_devices)] if not readings.empty else readings
        if view.empty:
            st.caption("Select devices in the sidebar (or wait for data).")
        else:
            c = st.columns(3)
            for col, (field, label) in zip(c, [("temperature_c", "Temperature (°C)"), ("humidity_pct", "Humidity (%)"),
                                               ("soil_moisture_pct", "Soil moisture (%)")]):
                fig = px.line(view, x="time", y=field, color="device_id", title=label, height=320)
                fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), legend_title_text="", xaxis_title="")
                col.plotly_chart(fig, use_container_width=True)
            latest = view.sort_values("ts_received").groupby("device_id").tail(1)[
                ["device_id", "seq", "temperature_c", "humidity_pct", "soil_moisture_pct", "time"]]
            st.dataframe(latest, hide_index=True, use_container_width=True)

    # ------------------------------------------------------------ performance
    with tab_perf:
        st.markdown(f"Delivery latency = device → broker → gateway → broker → collector, measured with a "
                    f"shared high-resolution clock on this host. Connection setup is NOT included. {MEAS}",
                    unsafe_allow_html=True)
        if not readings.empty:
            b = readings.set_index("time").resample("5s")
            agg = pd.DataFrame({"msgs_per_s": b["seq"].count() / 5,
                                "median_ms": b["latency_ms"].median(),
                                "p95_ms": b["latency_ms"].quantile(0.95)}).reset_index()
            c1, c2 = st.columns(2)
            fig = px.line(agg, x="time", y=["median_ms", "p95_ms"], title="Latency per 5 s window (ms)", height=330,
                          color_discrete_map={"median_ms": "#10b981", "p95_ms": "#f59e0b"})
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), legend_title_text="", xaxis_title="")
            c1.plotly_chart(fig, use_container_width=True)
            fig = px.bar(agg, x="time", y="msgs_per_s", title="Throughput (messages/s, 5 s windows)", height=330)
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="")
            c2.plotly_chart(fig, use_container_width=True)
            p99 = readings["latency_ms"].quantile(0.99)
            shown = readings[readings["latency_ms"] <= p99]
            fig = px.histogram(shown, x="latency_ms", nbins=60, height=300,
                               title=f"Latency distribution (up to p99 = {p99:.2f} ms; max {readings['latency_ms'].max():.2f} ms)")
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(fig, use_container_width=True)
        if not res.empty:
            res["time"] = local_time(res["ts"])
            c1, c2 = st.columns(2)
            fig = px.line(res, x="time", y="cpu_pct", color="process", title="CPU (% of one core)", height=300)
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), legend_title_text="", xaxis_title="")
            c1.plotly_chart(fig, use_container_width=True)
            fig = px.line(res, x="time", y="rss_mb", color="process", title="Memory (RSS, MB)", height=300)
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), legend_title_text="", xaxis_title="")
            c2.plotly_chart(fig, use_container_width=True)
        if not conns.empty:
            conns["time"] = local_time(conns["ts"])
            counts = conns["event"].value_counts().rename_axis("event").reset_index(name="count")
            c1, c2 = st.columns([1, 2])
            c1.markdown("**Connection events**")
            c1.dataframe(counts, hide_index=True, use_container_width=True)
            c2.dataframe(conns[["time", "event", "client_id", "username", "detail", "mode"]].tail(200)
                         .sort_values("time", ascending=False), hide_index=True, use_container_width=True, height=240)

    # ------------------------------------------------------------ security
    with tab_sec:
        st.markdown(f"Events from the gateway (message validation) and from Mosquitto's log "
                    f"(authentication, TLS, ACL). {MEAS}", unsafe_allow_html=True)
        if sec.empty:
            st.success("No security events in this time range.")
        else:
            sec["time"] = local_time(sec["ts"])
            sec["what"] = sec["event_type"].map(SECURITY_LABELS).fillna(sec["event_type"])
            types = sorted(sec["what"].unique())
            chosen = st.multiselect("Event types", types, default=types, key="sec_types")
            view = sec[sec["what"].isin(chosen)]
            c1, c2 = st.columns([1, 2])
            counts = view["what"].value_counts().rename_axis("event").reset_index(name="count")
            fig = px.bar(counts, x="count", y="event", orientation="h", title="Events by type", height=360)
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), yaxis_title="")
            c1.plotly_chart(fig, use_container_width=True)
            fig = px.scatter(view, x="time", y="what", color="source", title="Timeline", height=360)
            fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), yaxis_title="", xaxis_title="")
            c2.plotly_chart(fig, use_container_width=True)
            st.dataframe(view[["time", "source", "what", "device_id", "client_id", "detail", "mode"]]
                         .sort_values("time", ascending=False), hide_index=True, use_container_width=True, height=300)

    # ------------------------------------------------------------ export
    with tab_export:
        st.markdown("Download the data in the selected time range as CSV.")
        c = st.columns(3)
        c[0].download_button("Readings CSV", readings.drop(columns=["time"], errors="ignore").to_csv(index=False),
                             "readings.csv", "text/csv", disabled=readings.empty)
        c[1].download_button("Security events CSV", sec.drop(columns=["time", "what"], errors="ignore").to_csv(index=False),
                             "security_events.csv", "text/csv", disabled=sec.empty)
        c[2].download_button("Resource samples CSV", res.drop(columns=["time"], errors="ignore").to_csv(index=False),
                             "resource_samples.csv", "text/csv", disabled=res.empty)
    st.caption(f"Updated {time.strftime('%H:%M:%S')}")


if auto:
    st.fragment(run_every=5)(live_body)()
else:
    live_body()

# ---------------------------------------------------------------- benchmarks (static, not auto-refreshed)
st.divider()
st.header("📊 Benchmark results: Experiments A / B / C")
st.markdown(f"A = plain TCP, B = TLS (server certificate), C = mutual TLS. All runs on localhost. "
            f"These show the **relative** cost of TLS on this laptop, not real-network performance. {MEAS}",
            unsafe_allow_html=True)
runs_dirs = sorted([d for d in BENCH_DIR.glob("*") if (d / "summary.csv").exists()], reverse=True) if BENCH_DIR.exists() else []
if not runs_dirs:
    st.info("No benchmark results yet. Run `powershell -ExecutionPolicy Bypass -File scripts\\run_benchmarks.ps1`.")
else:
    chosen = st.selectbox("Benchmark run", runs_dirs, format_func=lambda d: d.name)
    summary = pd.read_csv(chosen / "summary.csv")
    runs = pd.read_csv(chosen / "runs.csv")
    st.markdown("**Summary per configuration** (mean ± std across repetitions)")
    st.dataframe(summary, hide_index=True, use_container_width=True)
    order = [m for m in ["plain", "tls", "mtls"] if m in runs["mode"].unique()]
    c = st.columns(3)
    for col, (metric, title) in zip(c, [("lat_median_ms", "Median latency (ms)"), ("lat_p95_ms", "p95 latency (ms)"),
                                        ("connect_median_ms", "Connection setup, median (ms)")]):
        fig = px.box(runs, x="mode", y=metric, color="mode", points="all", category_orders={"mode": order},
                     color_discrete_map=MODE_COLORS, title=title, height=330)
        fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="")
        col.plotly_chart(fig, use_container_width=True)
    c = st.columns(3)
    for col, (metric, title) in zip(c, [("throughput_mps", "Throughput (msg/s)"), ("success_rate", "Delivery success rate"),
                                        ("broker_cpu_avg", "Broker CPU (% of one core)")]):
        fig = px.box(runs, x="mode", y=metric, color="mode", points="all", category_orders={"mode": order},
                     color_discrete_map=MODE_COLORS, title=title, height=330)
        fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="")
        col.plotly_chart(fig, use_container_width=True)
    lat_file = chosen / "latencies.csv"
    if lat_file.exists():
        lat = pd.read_csv(lat_file)
        fig = px.ecdf(lat, x="latency_ms", color="mode", color_discrete_map=MODE_COLORS,
                      title="Latency CDF (all measured messages)", height=360)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)
    sec_file = chosen / "security_attempts.csv"
    if sec_file.exists():
        st.markdown("**Unauthorised connection attempts during the benchmark** (all should be rejected)")
        st.dataframe(pd.read_csv(sec_file), hide_index=True, use_container_width=True)
    st.markdown("**Download raw results**")
    c = st.columns(5)
    for col, name in zip(c, ["runs.csv", "summary.csv", "latencies.csv", "connect_times.csv", "resources.csv"]):
        f = chosen / name
        if f.exists():
            col.download_button(name, f.read_bytes(), name, "text/csv", key=f"dl_{name}")
    with st.expander("Benchmark configuration"):
        st.code((chosen / "config.json").read_text(encoding="utf-8"), language="json")
