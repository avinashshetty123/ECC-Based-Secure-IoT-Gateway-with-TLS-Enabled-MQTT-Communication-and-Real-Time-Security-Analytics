"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { usePoll } from "@/lib/live";
import { LineChart, MODE_COLORS, ModeBars } from "@/components/charts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>;
interface Bench {
  id: string; summary: Row[]; runs: Row[]; security: Row[];
  config: Row; environment: Row; cdf: Record<string, { q: number; ms: number }[]>;
}

const NAME: Record<string, string> = { plain: "A · Plain TCP", tls: "B · TLS (ECC)", mtls: "C · Mutual TLS" };
const ORDER = ["plain", "tls", "mtls"];

function findings(b: Bench): string[] {
  const by = Object.fromEntries(b.summary.map((s) => [s.mode, s]));
  const out: string[] = [];
  const p = by.plain, t = by.tls, m = by.mtls;
  if (p && t) {
    const d = t.pooled_lat_median_ms - p.pooled_lat_median_ms;
    out.push(`TLS added ${d.toFixed(3)} ms (${t.lat_median_overhead_vs_plain_pct}%) to the median delivery latency (${p.pooled_lat_median_ms.toFixed(3)} → ${t.pooled_lat_median_ms.toFixed(3)} ms).`);
    out.push(`Connection setup went from ${p.connect_median_ms_mean.toFixed(2)} ms (plain) to ${t.connect_median_ms_mean.toFixed(2)} ms with TLS (+${t.connect_overhead_vs_plain_pct}%): the ECDHE + ECDSA handshake is a one-time cost per connection.`);
  }
  if (p && m) {
    out.push(`Mutual TLS: median latency ${m.pooled_lat_median_ms.toFixed(3)} ms (${m.lat_median_overhead_vs_plain_pct}% vs plain), connection setup ${m.connect_median_ms_mean.toFixed(2)} ms (+${m.connect_overhead_vs_plain_pct}%). The extra client-certificate check is paid once at connect time.`);
  }
  const succ = b.summary.map((s) => s.success_rate_mean);
  if (succ.length) out.push(`Delivery success rate: ${b.summary.map((s) => `${s.mode} ${(s.success_rate_mean * 100).toFixed(2)}%`).join(", ")}. Every configuration sustained the offered ${b.summary[0].throughput_mps_mean.toFixed(0)} msg/s.`);
  if (b.security.length) {
    const ok = b.security.filter((r) => r.result === "PASS").length;
    out.push(`Security: ${ok}/${b.security.length} unauthorised attempt types were rejected on every try (${b.security.reduce((a, r) => a + r.rejected, 0)} rejected attempts in total).`);
  }
  return out;
}

export default function BenchmarksPage() {
  const { data: list } = usePoll<{ id: string }[]>("/api/benchmarks", 0);
  const [run, setRun] = useState("latest");
  const { data: b, error } = usePoll<Bench>(`/api/benchmarks/${run}`, 0);

  const bars = (key: string, std?: string) => ORDER.filter((m) => b?.summary.some((s) => s.mode === m)).map((m) => {
    const s = b!.summary.find((x) => x.mode === m)!;
    return { mode: m, label: NAME[m], mean: s[key] ?? null, std: std ? s[std] ?? null : null };
  });

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Benchmarks: Experiments A / B / C</h1>
          <p>
            The same load was run against plain MQTT (A), MQTT over TLS with an ECC server certificate (B) and mutual TLS (C), each
            with a fresh broker and gateway, a warm-up period and several repetitions. All numbers below are measured, raw CSVs are in{" "}
            <code>backend/reports/benchmarks/&lt;run&gt;/</code>.
          </p>
        </div>
        <div className="spacer" />
        <select value={run} onChange={(e) => setRun(e.target.value)}>
          <option value="latest">Latest run</option>
          {(list ?? []).map((r) => <option key={r.id} value={r.id}>{r.id}</option>)}
        </select>
      </div>

      {!b && (
        <div className="card empty">
          {error ? (
            <>No benchmark results yet. Run <code>powershell -ExecutionPolicy Bypass -File backend\scripts\run_benchmarks.ps1</code> (about 8 minutes, stop the live session first).</>
          ) : "Loading…"}
        </div>
      )}

      {b && (
        <>
          <motion.section className="card" style={{ marginBottom: 16 }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <h2 className="card-title">Key findings (computed from run {b.id})</h2>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {findings(b).map((t, i) => (
                <motion.li key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 + i * 0.08 }} style={{ marginBottom: 6 }}>
                  {t}
                </motion.li>
              ))}
            </ul>
            <div className="callout" style={{ marginTop: 10 }}>
              Localhost results show the <b>relative</b> cost of TLS on this laptop. They do not represent real network latency,
              where the network delay usually dominates.
            </div>
          </motion.section>

          <div className="three" style={{ marginBottom: 16 }}>
            <section className="card"><h2 className="card-title">Median latency (pooled)</h2><ModeBars unit="ms" decimals={3} items={bars("pooled_lat_median_ms")} /></section>
            <section className="card"><h2 className="card-title">p95 latency (pooled)</h2><ModeBars unit="ms" decimals={3} items={bars("pooled_lat_p95_ms")} /></section>
            <section className="card"><h2 className="card-title">Connection setup, median (mean ± std)</h2><ModeBars unit="ms" items={bars("connect_median_ms_mean", "connect_median_ms_std")} /></section>
          </div>
          <div className="three" style={{ marginBottom: 16 }}>
            <section className="card"><h2 className="card-title">Throughput (mean ± std)</h2><ModeBars unit="msg/s" decimals={1} items={bars("throughput_mps_mean", "throughput_mps_std")} /></section>
            <section className="card"><h2 className="card-title">Broker CPU (% of one core)</h2><ModeBars unit="%" items={bars("broker_cpu_avg_mean", "broker_cpu_avg_std")} /></section>
            <section className="card">
              <h2 className="card-title">Gateway CPU (% of one core)</h2>
              {b.summary.every((s) => !s.gateway_cpu_avg_mean) ? (
                <div className="callout">
                  Not valid in this run: it measured the Windows venv <i>launcher</i> process (≈0 %) instead of the real gateway
                  interpreter. Fixed in the harness. Re-run the benchmark to get real gateway CPU numbers.
                </div>
              ) : <ModeBars unit="%" items={bars("gateway_cpu_avg_mean", "gateway_cpu_avg_std")} />}
            </section>
          </div>

          <section className="card" style={{ marginBottom: 16 }}>
            <h2 className="card-title">Latency CDF: share of messages delivered within X ms</h2>
            <LineChart
              height={260}
              xFormat={(v) => `${v.toFixed(1)} ms`}
              yFormat={(v) => `${v.toFixed(0)}%`}
              series={ORDER.filter((m) => b.cdf[m]).map((m) => ({
                name: NAME[m], color: MODE_COLORS[m],
                points: b.cdf[m].filter((p) => p.q <= 0.98).map((p) => ({ x: p.ms, y: p.q * 100 })),
              }))}
            />
            <p className="muted small">Curves further left are faster. Cut at the 98th percentile so rare outliers don&apos;t hide the shape.</p>
          </section>

          <div className="two" style={{ marginBottom: 16 }}>
            <section className="card">
              <h2 className="card-title">Methodology</h2>
              <table className="tbl"><tbody>
                <tr><td>Devices × rate</td><td>{b.config.devices} × {b.config.rate_hz_per_device} msg/s = {b.config.devices * b.config.rate_hz_per_device} msg/s offered</td></tr>
                <tr><td>QoS</td><td>{b.config.qos}</td></tr>
                <tr><td>Warm-up / window / drain</td><td>{b.config.warmup_s} s / {b.config.duration_s} s / {b.config.drain_s} s</td></tr>
                <tr><td>Repetitions</td><td>{b.config.repetitions} per mode, interleaved A,B,C,A,B,C…</td></tr>
                <tr><td>Connection samples</td><td>{b.config.connect_samples} per run (idle system, before the load)</td></tr>
                <tr><td>Latency</td><td>device → broker → gateway → broker → sink, perf_counter_ns (one clock, same host)</td></tr>
                <tr><td>CPU / RAM</td><td>psutil every {b.config.resource_sample_interval_s} s during the measurement window</td></tr>
              </tbody></table>
            </section>
            <section className="card">
              <h2 className="card-title">Environment</h2>
              <table className="tbl"><tbody>
                {Object.entries(b.environment).map(([k, v]) => <tr key={k}><td>{k}</td><td>{String(v)}</td></tr>)}
              </tbody></table>
            </section>
          </div>

          {b.security.length > 0 && (
            <section className="card" style={{ marginBottom: 16 }}>
              <h2 className="card-title">Unauthorised connection attempts (all must be rejected)</h2>
              <div className="tbl-wrap"><table className="tbl">
                <thead><tr><th>mode</th><th>attempt</th><th>tries</th><th>rejected</th><th>result</th><th>client-side reason</th></tr></thead>
                <tbody>{b.security.map((r, i) => (
                  <tr key={i}><td>{r.mode}</td><td>{r.attempt}</td><td>{r.attempts}</td><td>{r.rejected}</td>
                    <td className={r.result === "PASS" ? "pass-txt" : "fail-txt"}>{r.result}</td><td className="small">{r.client_side_reason}</td></tr>
                ))}</tbody>
              </table></div>
            </section>
          )}

          <section className="card">
            <h2 className="card-title">Every run (raw)</h2>
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>run</th><th>sent</th><th>received</th><th>success</th><th>median ms</th><th>p95 ms</th><th>connect ms</th><th>broker CPU %</th><th>broker RSS MB</th></tr></thead>
              <tbody>{b.runs.map((r) => (
                <tr key={r.run_id}><td className="mono small">{r.mode}-r{r.repetition}</td><td>{r.sent}</td><td>{r.received}</td>
                  <td>{(r.success_rate * 100).toFixed(2)}%</td><td>{r.lat_median_ms?.toFixed(3)}</td><td>{r.lat_p95_ms?.toFixed(3)}</td>
                  <td>{r.connect_median_ms?.toFixed(2)}</td><td>{r.broker_cpu_avg?.toFixed(2)}</td><td>{r.broker_rss_max_mb?.toFixed(1)}</td></tr>
              ))}</tbody>
            </table></div>
          </section>
        </>
      )}
    </main>
  );
}
