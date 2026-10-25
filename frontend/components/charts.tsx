"use client";

/** Small dependency-free SVG charts (animated with framer-motion). */
import { motion } from "framer-motion";

export const MODE_COLORS: Record<string, string> = { plain: "#f59e0b", tls: "#10b981", mtls: "#3b82f6" };
const W = 600;

function niceTicks(min: number, max: number, n = 4): number[] {
  if (!isFinite(min) || !isFinite(max)) return [];
  if (min === max) return [min];
  const step = (max - min) / n;
  return Array.from({ length: n + 1 }, (_, i) => min + i * step);
}
const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));

// ------------------------------------------------------------------ sparkline
export function Sparkline({ values, color, height = 70 }: { values: number[]; color: string; height?: number }) {
  if (values.length < 2) return <svg className="chart" viewBox={`0 0 200 ${height}`} />;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 200},${height - 4 - ((v - min) / span) * (height - 8)}`).join(" ");
  return (
    <svg className="chart" viewBox={`0 0 200 ${height}`} preserveAspectRatio="none" style={{ height }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <circle cx={200} cy={height - 4 - ((values[values.length - 1] - min) / span) * (height - 8)} r="3" fill={color} />
    </svg>
  );
}

// ------------------------------------------------------------------ line chart
export interface Series { name: string; color: string; points: { x: number; y: number }[] }

export function LineChart({ series, height = 230, xFormat = fmt, yFormat = fmt, yLabel }: {
  series: Series[]; height?: number; xFormat?: (v: number) => string; yFormat?: (v: number) => string; yLabel?: string;
}) {
  const all = series.flatMap((s) => s.points).filter((p) => p.y != null && isFinite(p.y));
  if (all.length < 2) return <div className="empty">Not enough data yet.</div>;
  const L = 52, R = 12, T = 10, B = 26, h = height;
  const xmin = Math.min(...all.map((p) => p.x)), xmax = Math.max(...all.map((p) => p.x));
  let ymin = Math.min(...all.map((p) => p.y)), ymax = Math.max(...all.map((p) => p.y));
  const pad = (ymax - ymin) * 0.1 || Math.abs(ymax) * 0.1 || 1;
  ymin = ymin >= 0 ? Math.max(0, ymin - pad) : ymin - pad; // never dip below 0 for positive data
  ymax += pad;
  const sx = (x: number) => L + ((x - xmin) / (xmax - xmin || 1)) * (W - L - R);
  const sy = (y: number) => T + (1 - (y - ymin) / (ymax - ymin || 1)) * (h - T - B);
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${h}`}>
        {niceTicks(ymin, ymax).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} />
            <text className="tick" x={L - 6} y={sy(t) + 3} textAnchor="end">{yFormat(t)}</text>
          </g>
        ))}
        {niceTicks(xmin, xmax, 4).map((t) => (
          <text key={t} className="tick" x={sx(t)} y={h - 8} textAnchor="middle">{xFormat(t)}</text>
        ))}
        <line className="axis" x1={L} x2={L} y1={T} y2={h - B} />
        <line className="axis" x1={L} x2={W - R} y1={h - B} y2={h - B} />
        {yLabel && <text className="tick" x={12} y={T + 4}>{yLabel}</text>}
        {series.map((s) => {
          const pts = s.points.filter((p) => p.y != null && isFinite(p.y));
          if (pts.length < 2) return null;
          const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
          return (
            <motion.path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth={2}
              initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.8 }} />
          );
        })}
      </svg>
      {series.length > 1 && (
        <div className="chart-legend">
          {series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ horizontal bars
export function HBarChart({ items, valueFormat = (v) => String(v) }: {
  items: { label: string; value: number; color?: string }[]; valueFormat?: (v: number) => string;
}) {
  if (!items.length) return <div className="empty">Nothing recorded in this time range.</div>;
  const max = Math.max(...items.map((i) => i.value)) || 1;
  const rowH = 28, labelW = 200, h = items.length * rowH + 6;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${h}`}>
      {items.map((it, i) => {
        const w = ((W - labelW - 60) * it.value) / max;
        return (
          <g key={it.label} transform={`translate(0, ${i * rowH + 4})`}>
            <text className="tick" x={labelW - 8} y={15} textAnchor="end" style={{ fontSize: 12, fill: "var(--text)" }}>{it.label}</text>
            <motion.rect x={labelW} y={3} height={18} rx={4} fill={it.color ?? "#60a5fa"}
              initial={{ width: 0 }} animate={{ width: Math.max(w, 2) }} transition={{ duration: 0.6, delay: i * 0.05 }} />
            <text className="tick" x={labelW + Math.max(w, 2) + 6} y={16}>{valueFormat(it.value)}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ------------------------------------------------------------------ histogram
export function Histogram({ bins, color = "#60a5fa", height = 200 }: {
  bins: { from: number; to: number; count: number }[]; color?: string; height?: number;
}) {
  if (!bins.length) return <div className="empty">Not enough data yet.</div>;
  const L = 44, R = 10, T = 8, B = 26;
  const max = Math.max(...bins.map((b) => b.count)) || 1;
  const bw = (W - L - R) / bins.length;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${height}`}>
      {niceTicks(0, max, 3).map((t) => (
        <g key={t}>
          <line className="grid-line" x1={L} x2={W - R} y1={T + (1 - t / max) * (height - T - B)} y2={T + (1 - t / max) * (height - T - B)} />
          <text className="tick" x={L - 6} y={T + (1 - t / max) * (height - T - B) + 3} textAnchor="end">{Math.round(t)}</text>
        </g>
      ))}
      {bins.map((b, i) => {
        const bh = (b.count / max) * (height - T - B);
        return (
          <motion.rect key={i} x={L + i * bw + 1} width={Math.max(bw - 2, 1)} fill={color} rx={2}
            initial={{ y: height - B, height: 0 }} animate={{ y: height - B - bh, height: bh }} transition={{ duration: 0.5, delay: i * 0.01 }}>
            <title>{`${b.from.toFixed(2)}–${b.to.toFixed(2)} ms: ${b.count}`}</title>
          </motion.rect>
        );
      })}
      {[0, Math.floor(bins.length / 2), bins.length - 1].map((i) => (
        <text key={i} className="tick" x={L + i * bw + bw / 2} y={height - 8} textAnchor="middle">{bins[i].from.toFixed(2)} ms</text>
      ))}
      <line className="axis" x1={L} x2={W - R} y1={height - B} y2={height - B} />
    </svg>
  );
}

// ------------------------------------------------------------------ per-mode bars with error whiskers
export function ModeBars({ items, unit, height = 220, decimals = 2 }: {
  items: { mode: string; label: string; mean: number | null; std?: number | null }[]; unit: string; height?: number; decimals?: number;
}) {
  const vals = items.filter((i) => i.mean != null);
  if (!vals.length) return <div className="empty">No data.</div>;
  const L = 44, R = 10, T = 22, B = 30;
  const max = Math.max(...vals.map((i) => (i.mean ?? 0) + (i.std ?? 0))) * 1.12 || 1;
  const slot = (W - L - R) / items.length, bw = Math.min(90, slot * 0.55);
  const sy = (v: number) => T + (1 - v / max) * (height - T - B);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${height}`}>
      {niceTicks(0, max, 3).map((t) => (
        <g key={t}>
          <line className="grid-line" x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} />
          <text className="tick" x={L - 6} y={sy(t) + 3} textAnchor="end">{fmt(t)}</text>
        </g>
      ))}
      {items.map((it, i) => {
        if (it.mean == null) return null;
        const cx = L + slot * i + slot / 2, top = sy(it.mean);
        return (
          <g key={it.mode}>
            <motion.rect x={cx - bw / 2} width={bw} rx={5} fill={MODE_COLORS[it.mode] ?? "#60a5fa"}
              initial={{ y: height - B, height: 0 }} animate={{ y: top, height: height - B - top }} transition={{ duration: 0.7, delay: i * 0.12 }} />
            {it.std != null && it.std > 0 && (
              <g stroke="#e2e8f0" strokeWidth={1.4}>
                <line x1={cx} x2={cx} y1={sy(it.mean + it.std)} y2={sy(Math.max(it.mean - it.std, 0))} />
                <line x1={cx - 8} x2={cx + 8} y1={sy(it.mean + it.std)} y2={sy(it.mean + it.std)} />
                <line x1={cx - 8} x2={cx + 8} y1={sy(Math.max(it.mean - it.std, 0))} y2={sy(Math.max(it.mean - it.std, 0))} />
              </g>
            )}
            <text x={cx} y={sy(it.mean + (it.std ?? 0)) - 6} textAnchor="middle" style={{ fill: "var(--text)", fontSize: 12, fontWeight: 700 }}>
              {it.mean.toFixed(decimals)} {unit}
            </text>
            <text className="tick" x={cx} y={height - 10} textAnchor="middle" style={{ fontSize: 12 }}>{it.label}</text>
          </g>
        );
      })}
      <line className="axis" x1={L} x2={W - R} y1={height - B} y2={height - B} />
    </svg>
  );
}
