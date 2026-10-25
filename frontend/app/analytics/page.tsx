"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { API } from "@/lib/api";
import { useLive, usePoll } from "@/lib/live";
import { HBarChart, Histogram, LineChart, type Series } from "@/components/charts";

interface Overview {
  kpi: {
    messages: number; msgs_per_s: number; devices_active: number; lat_median_ms: number | null; lat_p95_ms: number | null;
    lat_p99_ms?: number; rejected_messages: number; connection_blocks: number;
  };
  series: { t: number; msgs_per_s: number; median_ms: number; p95_ms: number }[];
  histogram: { from: number; to: number; count: number }[];
  security_counts: { type: string; count: number }[];
  security_recent: { ts: number; source: string; event_type: string; device_id: string | null; client_id: string | null; detail: string }[];
  connections: { event: string; n: number }[];
  resources: { t: number; process: string; cpu_pct: number; rss_mb: number }[];
}
interface Sensors {
  devices: string[]; selected: string[];
  series: Record<string, { ts_received: number; temperature_c: number; humidity_pct: number; soil_moisture_pct: number }[]>;
  latest: { device_id: string; seq: number; temperature_c: number; humidity_pct: number; soil_moisture_pct: number; ts_received: number }[];
}

const SEC_LABELS: Record<string, string> = {
  auth_failed: "Login refused", tls_cert_verify_failed: "Bad client certificate", tls_no_client_cert: "No client certificate",
  tls_client_rejected_broker_cert: "Client refused broker cert", tls_protocol_mismatch: "Non-TLS on TLS port",
  tls_error: "Other TLS error", acl_denied_publish: "ACL: publish denied", schema_rejected: "Invalid message (gateway)",
  replay_rejected: "Replayed message (gateway)", sequence_gap: "Sequence gap", device_restart: "Device restart",
};
const SEC_COLORS: Record<string, string> = { schema_rejected: "#f59e0b", replay_rejected: "#fb923c", acl_denied_publish: "#a78bfa", sequence_gap: "#64748b", device_restart: "#64748b" };
const PROC_COLORS: Record<string, string> = { broker: "#22c55e", backend: "#60a5fa", gateway: "#a78bfa", collector: "#2dd4bf", fleet: "#f59e0b" };
const DEV_COLORS = ["#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb7185", "#22d3ee", "#a3e635"];
const WINDOWS = [{ v: "300", l: "Last 5 minutes" }, { v: "900", l: "Last 15 minutes" }, { v: "3600", l: "Last hour" }, { v: "86400", l: "Last 24 hours" }, { v: "all", l: "All data" }];

const hms = (t: number) => new Date(t * 1000).toTimeString().slice(0, 8);
const f = (v: number | null | undefined, d = 2, u = "") => (v == null ? "-" : `${v.toFixed(d)}${u}`);

function Kpi({ k, v, h, i }: { k: string; v: string; h?: string; i: number }) {
  return (
    <motion.div className="kpi" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
      <div className="k">{k}</div>
      <motion.div className="v2" key={v} initial={{ opacity: 0.4 }} animate={{ opacity: 1 }}>{v}</motion.div>
      {h && <div className="h">{h}</div>}
    </motion.div>
  );
}

export default function AnalyticsPage() {
  const { session, send } = useLive();
  const [win, setWin] = useState("300");
  const [picked, setPicked] = useState<string[]>([]);
  const { data: ov } = usePoll<Overview>(`/api/analytics/overview?window=${win}`, 3000);
  const { data: sens } = usePoll<Sensors>(`/api/analytics/sensors?window=${win}&devices=${picked.join(",")}`, 4000);

  const selected = sens?.selected ?? [];
  const sensorSeries = useMemo(() => {
    const out: Record<"temperature_c" | "humidity_pct" | "soil_moisture_pct", Series[]> = { temperature_c: [], humidity_pct: [], soil_moisture_pct: [] };
    if (!sens) return out;
    selected.forEach((dev, i) => {
      const pts = sens.series[dev] ?? [];
      for (const k of Object.keys(out) as (keyof typeof out)[]) {
        out[k].push({ name: dev, color: DEV_COLORS[i % DEV_COLORS.length], points: pts.map((p) => ({ x: p.ts_received, y: p[k] })) });
      }
    });
    return out;
  }, [sens, selected]);

  const resSeries = (field: "cpu_pct" | "rss_mb"): Series[] => {
    const by: Record<string, { x: number; y: number }[]> = {};
    for (const r of ov?.resources ?? []) (by[r.process] ??= []).push({ x: r.t, y: r[field] });
    return Object.entries(by).map(([name, points]) => ({ name, color: PROC_COLORS[name] ?? "#94a3b8", points }));
  };

  const toggleDev = (d: string) => {
    const base = picked.length ? picked : selected;
    setPicked(base.includes(d) ? base.filter((x) => x !== d) : [...base, d]);
  };
  const k = ov?.kpi;
  const noData = !k || k.messages === 0;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Real-time analytics</h1>
          <p>
            Everything the collector stored in SQLite: validated readings with measured latency, gateway rejections, broker
            authentication/TLS/ACL failures, and CPU/RAM of each process. Sensor values are{" "}
            <span className="badge sim">SIMULATED</span>; all other numbers are <span className="badge real">MEASURED</span> on this machine.
          </p>
        </div>
        <div className="spacer" />
        <div className="controls">
          <select value={win} onChange={(e) => setWin(e.target.value)}>
            {WINDOWS.map((w) => <option key={w.v} value={w.v}>{w.l}</option>)}
          </select>
          {session.running && (
            <button className={`btn ${session.fleet ? "danger" : "primary"}`}
              onClick={() => send("/api/fleet", { enabled: !session.fleet, devices: 8, rate: 1, invalid_every: 30 })}>
              {session.fleet ? "Stop fleet" : "Start 8-device fleet"}
            </button>
          )}
        </div>
      </div>

      {!session.running && noData && (
        <div className="callout" style={{ marginBottom: 16 }}>
          No data yet. Go to the <Link href="/">Live demo</Link>, press <b>Start</b>, then turn on <b>Run a fleet</b> (or press the
          button here). Readings, attacks and metrics will appear within seconds.
        </div>
      )}

      <div className="kpis" style={{ marginBottom: 16 }}>
        <Kpi i={0} k="Messages stored" v={k ? k.messages.toLocaleString() : "-"} h="in the time range" />
        <Kpi i={1} k="Throughput" v={k ? `${k.msgs_per_s.toFixed(1)}/s` : "-"} h="last 30 s" />
        <Kpi i={2} k="Devices active" v={k ? String(k.devices_active) : "-"} h="last 30 s" />
        <Kpi i={3} k="Median latency" v={f(k?.lat_median_ms, 2, " ms")} h="device → gateway → collector" />
        <Kpi i={4} k="p95 latency" v={f(k?.lat_p95_ms, 2, " ms")} h={k?.lat_p99_ms ? `p99 ${k.lat_p99_ms.toFixed(2)} ms` : undefined} />
        <Kpi i={5} k="Messages rejected" v={k ? String(k.rejected_messages) : "-"} h="schema / replay (gateway)" />
        <Kpi i={6} k="Connection & ACL blocks" v={k ? String(k.connection_blocks) : "-"} h="from Mosquitto's log" />
      </div>

      <div className="two" style={{ marginBottom: 16 }}>
        <section className="card">
          <h2 className="card-title">Delivery latency per 5 s window <span className="badge real">measured</span></h2>
          <LineChart xFormat={hms} yLabel="ms" series={[
            { name: "median", color: "#22c55e", points: (ov?.series ?? []).map((p) => ({ x: p.t, y: p.median_ms })) },
            { name: "p95", color: "#f59e0b", points: (ov?.series ?? []).map((p) => ({ x: p.t, y: p.p95_ms })) },
          ]} />
          <p className="muted small">Shared high-resolution clock on this host (perf_counter). Connection setup is not included.</p>
        </section>
        <section className="card">
          <h2 className="card-title">Throughput <span className="badge real">measured</span></h2>
          <LineChart xFormat={hms} yLabel="msg/s" series={[{ name: "messages/s", color: "#60a5fa", points: (ov?.series ?? []).map((p) => ({ x: p.t, y: p.msgs_per_s })) }]} />
          <p className="muted small">Validated readings stored per second, averaged over 5 s windows.</p>
        </section>
      </div>

      <div className="two" style={{ marginBottom: 16 }}>
        <section className="card">
          <h2 className="card-title">Latency distribution (up to p99)</h2>
          <Histogram bins={ov?.histogram ?? []} color="#60a5fa" />
        </section>
        <section className="card">
          <h2 className="card-title">Security events by type</h2>
          <HBarChart items={(ov?.security_counts ?? []).map((c) => ({ label: SEC_LABELS[c.type] ?? c.type, value: c.count, color: SEC_COLORS[c.type] ?? "#ef4444" }))} />
          {ov?.connections && ov.connections.length > 0 && (
            <p className="muted small">Connections: {ov.connections.map((c) => `${c.event} ${c.n}`).join(" · ")}</p>
          )}
        </section>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <h2 className="card-title">Sensor data per device <span className="badge sim">simulated values</span></h2>
        <div className="row" style={{ marginBottom: 10 }}>
          {(sens?.devices ?? []).map((d) => (
            <button key={d} className="chip" aria-pressed={selected.includes(d)} onClick={() => toggleDev(d)}>{d}</button>
          ))}
          {!sens?.devices.length && <span className="muted small">No devices have sent data in this time range.</span>}
        </div>
        <div className="three">
          <div><div className="muted small">Temperature (°C)</div><LineChart height={200} xFormat={hms} series={sensorSeries.temperature_c} /></div>
          <div><div className="muted small">Humidity (%)</div><LineChart height={200} xFormat={hms} series={sensorSeries.humidity_pct} /></div>
          <div><div className="muted small">Soil moisture (%)</div><LineChart height={200} xFormat={hms} series={sensorSeries.soil_moisture_pct} /></div>
        </div>
        {sens && sens.latest.length > 0 && (
          <div className="tbl-wrap" style={{ marginTop: 10 }}>
            <table className="tbl">
              <thead><tr><th>device</th><th>seq</th><th>temperature °C</th><th>humidity %</th><th>soil %</th><th>received</th></tr></thead>
              <tbody>
                {sens.latest.map((r) => (
                  <tr key={r.device_id}><td>{r.device_id}</td><td>{r.seq}</td><td>{r.temperature_c}</td><td>{r.humidity_pct}</td><td>{r.soil_moisture_pct}</td><td>{hms(r.ts_received)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="two" style={{ marginBottom: 16 }}>
        <section className="card">
          <h2 className="card-title">CPU (% of one core) <span className="badge real">psutil</span></h2>
          <LineChart xFormat={hms} yLabel="%" series={resSeries("cpu_pct")} />
        </section>
        <section className="card">
          <h2 className="card-title">Memory (RSS, MB) <span className="badge real">psutil</span></h2>
          <LineChart xFormat={hms} yLabel="MB" series={resSeries("rss_mb")} />
        </section>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <h2 className="card-title">Recent security events</h2>
        {ov?.security_recent?.length ? (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>time</th><th>source</th><th>event</th><th>device / client</th><th>detail</th></tr></thead>
              <tbody>
                {ov.security_recent.map((e, i) => (
                  <tr key={i}>
                    <td className="mono">{hms(e.ts)}</td><td>{e.source}</td>
                    <td><span className={`badge ${e.source === "gateway" ? "warn" : "bad"}`}>{SEC_LABELS[e.event_type] ?? e.event_type}</span></td>
                    <td>{e.device_id ?? e.client_id ?? "-"}</td><td>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty">No security events in this time range. Try the attack buttons on the Live demo.</div>}
      </section>

      <section className="card">
        <h2 className="card-title">Export (CSV, selected time range)</h2>
        <div className="row">
          {["readings", "security_events", "connection_events", "resource_samples"].map((t) => (
            <a key={t} className="btn" href={`${API}/api/export/${t}.csv?window=${win}`} download>{t}.csv</a>
          ))}
        </div>
      </section>
    </main>
  );
}
