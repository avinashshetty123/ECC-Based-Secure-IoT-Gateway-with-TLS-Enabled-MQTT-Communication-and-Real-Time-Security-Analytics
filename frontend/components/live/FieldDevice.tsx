"use client";

import { motion } from "framer-motion";
import type { Mode } from "@/lib/api";
import type { VizState } from "@/lib/visualizer";

type Pt = [number, number];

/* Wiring in the style of the usual ESP32 + DHT22 + capacitive soil sensor reference diagrams.
   red = 3V3, grey = GND, yellow = soil analog out (GPIO34), green = DHT22 data (GPIO4). */
const WIRES: { id: string; color: string; pts: Pt[]; data?: boolean }[] = [
  { id: "soilGnd", color: "#94a3b8", pts: [[236, 108], [236, 18], [440, 18], [440, 110], [526, 110]] },
  { id: "soilVcc", color: "#ef4444", pts: [[248, 108], [248, 24], [430, 24], [430, 100], [526, 100]] },
  { id: "soilOut", color: "#facc15", pts: [[260, 108], [260, 30], [420, 30], [420, 182], [526, 182]], data: true },
  { id: "dhtVcc", color: "#ef4444", pts: [[341, 154], [341, 176], [430, 176], [430, 100]] },
  { id: "dhtGnd", color: "#94a3b8", pts: [[377, 154], [377, 160], [440, 160], [440, 110]] },
  { id: "dhtData", color: "#22c55e", pts: [[353, 154], [353, 168], [450, 168], [450, 164], [526, 164]], data: true },
];
const pathOf = (pts: Pt[]) => pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join(" ");
const last = (a: number[]) => (a.length ? a[a.length - 1] : null);

/**
 * The field device artwork as an SVG <g> (own coordinates 0..700 x 0..300),
 * embedded by the Scene with a transform.
 */
export function FieldArt({ sensors, flash, mode }: { sensors: VizState["sensors"]; flash: VizState["flash"]; mode: Mode }) {
  const t = last(sensors.T), h = last(sensors.H), m = last(sensors.M);
  const sun = t == null ? 0.35 : Math.min(1, Math.max(0.2, (t - 10) / 25));
  const wet = m == null ? 0.15 : Math.min(0.65, (m / 100) * 0.75);
  const sampled = flash.sensors.n;
  const published = flash.device.n;

  return (
    <g>
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#0b1530" /><stop offset="1" stopColor="#14254a" /></linearGradient>
        <linearGradient id="soil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#6b4423" /><stop offset="1" stopColor="#3b2412" /></linearGradient>
        <linearGradient id="shield" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#e2e8f0" /><stop offset="1" stopColor="#94a3b8" /></linearGradient>
        <radialGradient id="sunGlow"><stop offset="0" stopColor="#fde047" stopOpacity="0.9" /><stop offset="1" stopColor="#fde047" stopOpacity="0" /></radialGradient>
      </defs>

      <rect x="0" y="0" width="480" height="210" fill="url(#sky)" rx="12" />
      <circle cx="60" cy="56" r={34 + sun * 26} fill="url(#sunGlow)" opacity={sun} />
      <circle cx="60" cy="56" r="16" fill="#fde047" opacity={0.5 + sun / 2} />
      <rect x="0" y="200" width="480" height="100" fill="url(#soil)" rx="6" />
      <rect x="0" y="200" width="480" height="100" fill="#2563eb" opacity={wet} rx="6" style={{ transition: "opacity 1s" }} />
      {Array.from({ length: 40 }, (_, i) => (
        <circle key={i} cx={(i * 53) % 470 + 6} cy={212 + ((i * 37) % 80)} r={1.5 + (i % 3)} fill="#2a1a0c" opacity="0.6" />
      ))}

      <motion.g style={{ originX: "120px", originY: "200px" }} animate={{ rotate: [-2, 2, -2] }} transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}>
        <path d="M120 200 C 118 170, 124 150, 120 118" stroke="#16a34a" strokeWidth="4" fill="none" />
        <ellipse cx="102" cy="150" rx="18" ry="7" fill="#22c55e" transform="rotate(-25 102 150)" />
        <ellipse cx="139" cy="138" rx="18" ry="7" fill="#22c55e" transform="rotate(25 139 138)" />
        <ellipse cx="108" cy="122" rx="14" ry="6" fill="#4ade80" transform="rotate(-30 108 122)" />
        <ellipse cx="134" cy="112" rx="13" ry="6" fill="#4ade80" transform="rotate(30 134 112)" />
      </motion.g>

      {WIRES.map((w) => (
        <path key={w.id} d={pathOf(w.pts)} stroke={w.color} strokeWidth="3" fill="none" strokeLinejoin="round" strokeLinecap="round" opacity="0.9" />
      ))}

      {/* capacitive soil moisture sensor v1.2 */}
      <path d="M222 112 h52 v40 l-8 120 l-18 8 l-18 -8 l-8 -120 z" fill="#111827" stroke="#334155" />
      <rect x="230" y="118" width="14" height="14" fill="#1f2937" stroke="#475569" />
      <text x="248" y="146" fontSize="7" fill="#e5e7eb" textAnchor="middle">v1.2</text>
      {[236, 248, 260].map((x) => <rect key={x} x={x - 2} y="104" width="4" height="8" fill="#fbbf24" />)}
      <rect x="216" y="200" width="66" height="84" fill="url(#soil)" opacity="0.55" />
      <rect x="216" y="200" width="66" height="84" fill="#2563eb" opacity={wet * 0.55} />
      <text x="248" y="296" fontSize="17" fontWeight="600" textAnchor="middle" fill="#fde68a">soil-moisture probe</text>

      {/* DHT22 / AM2302 */}
      <rect x="330" y="66" width="60" height="82" rx="5" fill="#f1f5f9" stroke="#cbd5e1" />
      {Array.from({ length: 6 }, (_, r) => Array.from({ length: 4 }, (_, c) => (
        <rect key={`${r}-${c}`} x={336 + c * 13} y={74 + r * 11} width="9" height="6" rx="1" fill="#94a3b8" />
      )))}
      {[341, 353, 365, 377].map((x) => <rect key={x} x={x - 1.5} y="148" width="3" height="8" fill="#fbbf24" />)}
      <rect x="282" y="40" width="156" height="22" rx="6" fill="#0b1530" opacity="0.9" />
      <text x="360" y="57" fontSize="16" fontWeight="600" textAnchor="middle" fill="#e2e8f0">DHT22 · temp + RH</text>

      {/* ESP32 DevKit */}
      <rect x="520" y="68" width="180" height="168" rx="8" fill="#0f2a4a" stroke="#1e40af" />
      <rect x="545" y="74" width="130" height="102" rx="3" fill="#1e293b" />
      <path d="M552 80 h12 v10 h10 v-10 h10 v10 h10 v-10 h10 v10 h10 v-10 h10 v10 h12" stroke="#d4a017" strokeWidth="2" fill="none" />
      <rect x="551" y="100" width="118" height="70" rx="3" fill="url(#shield)" />
      <text x="610" y="132" fontSize="15" fontWeight="700" textAnchor="middle" fill="#334155">ESP32-WROOM</text>
      <text x="610" y="152" fontSize="13" textAnchor="middle" fill="#475569">{mode === "mtls" ? "cert + private key" : mode === "tls" ? "trusts our CA" : "no TLS"}</text>
      {Array.from({ length: 15 }, (_, i) => (
        <g key={i}>
          <circle cx="528" cy={92 + i * 9.5} r="2.6" fill="#d4a017" />
          <circle cx="692" cy={92 + i * 9.5} r="2.6" fill="#d4a017" />
        </g>
      ))}
      <rect x="596" y="228" width="28" height="12" rx="2" fill="#cbd5e1" />
      <circle cx="560" cy="210" r="4" fill="#ef4444" />
      <motion.circle key={`led${published}`} cx="580" cy="210" r="4" fill="#3b82f6"
        initial={{ opacity: 0.25 }} animate={{ opacity: published ? [1, 0.25, 1, 0.25] : 0.25 }} transition={{ duration: 0.8 }} />
      <text x="610" y="198" fontSize="16" fontWeight="600" textAnchor="middle" fill="#93c5fd">ESP32 · dev-001</text>

      {sampled > 0 && WIRES.filter((w) => w.data).map((w) => (
        <motion.circle key={`${w.id}-${sampled}`} r="6" fill={w.color} style={{ filter: `drop-shadow(0 0 6px ${w.color})` }}
          initial={{ cx: w.pts[0][0], cy: w.pts[0][1], opacity: 1 }}
          animate={{ cx: w.pts.map((p) => p[0]), cy: w.pts.map((p) => p[1]), opacity: w.pts.map((_, i) => (i === w.pts.length - 1 ? 0.2 : 1)) }}
          transition={{ duration: 1.4, ease: "easeInOut" }} />
      ))}
      {published > 0 && [0, 1, 2].map((i) => (
        <motion.circle key={`wave${published}-${i}`} cx="610" cy="76" fill="none" stroke={mode === "plain" ? "#f5a524" : "#22c55e"} strokeWidth="2"
          initial={{ r: 6, opacity: 0.9 }} animate={{ r: 70, opacity: 0 }} transition={{ duration: 1.6, delay: i * 0.35, ease: "easeOut" }} />
      ))}

      <g fontSize="19" fontWeight="700">
        <text x="296" y="230" fill="#38bdf8">{h != null ? `💧 ${h.toFixed(1)} % RH` : ""}</text>
        <text x="296" y="254" fill="#fb7185">{t != null ? `🌡 ${t.toFixed(1)} °C` : ""}</text>
        <text x="296" y="278" fill="#a3e635">{m != null ? `🌱 ${m.toFixed(1)} % soil` : ""}</text>
      </g>
    </g>
  );
}

/** Arduino-style serial monitor of the latest readings (HTML). */
export function SerialMonitor({ sensors }: { sensors: VizState["sensors"] }) {
  const idx = sensors.T.map((_, i) => i).slice(-8);
  return (
    <div className="serial">
      <div className="serial-head">Serial monitor · dev-001 · 115200 baud</div>
      {idx.length === 0 && <div className="muted">waiting for first reading…</div>}
      {idx.map((i, k) => (
        <motion.div key={`${sensors.seq}-${i}`} initial={k === idx.length - 1 ? { opacity: 0, x: -6 } : false} animate={{ opacity: 1, x: 0 }}
          style={{ color: k === idx.length - 1 ? "#4ade80" : "#94a3b8" }}>
          T={sensors.T[i].toFixed(1)}°C  RH={sensors.H[i].toFixed(1)}%  SOIL={sensors.M[i].toFixed(1)}%
        </motion.div>
      ))}
    </div>
  );
}
