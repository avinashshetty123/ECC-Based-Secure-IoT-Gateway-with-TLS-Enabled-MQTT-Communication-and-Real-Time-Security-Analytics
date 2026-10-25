"use client";

import { motion } from "framer-motion";
import { Sparkline } from "@/components/charts";
import type { VizState } from "@/lib/visualizer";
import { SerialMonitor } from "./FieldDevice";

const TILES = [
  { key: "T", name: "Temperature (DHT22)", unit: "°C", cls: "t", hex: "#fb7185" },
  { key: "H", name: "Air humidity (DHT22)", unit: "%", cls: "h", hex: "#38bdf8" },
  { key: "M", name: "Soil moisture (capacitive probe)", unit: "%", cls: "m", hex: "#a3e635" },
] as const;

export default function SensorPanel({ sensors }: { sensors: VizState["sensors"] }) {
  return (
    <div className="sensor-panel">
      <div className="tiles">
        {TILES.map((t) => {
          const vals = sensors[t.key];
          const v = vals.length ? vals[vals.length - 1] : null;
          return (
            <div key={t.key} className={`tile ${t.cls}`}>
              <div className="name">{t.name}</div>
              <div>
                <motion.span key={v ?? "none"} className="val" initial={{ opacity: 0.3, y: -4 }} animate={{ opacity: 1, y: 0 }}>
                  {v != null ? v.toFixed(1) : "--"}
                </motion.span>
                <span className="unit">{t.unit}</span>
              </div>
              <Sparkline values={vals} color={t.hex} />
              <div className="range">
                {vals.length ? `last ${vals.length}: min ${Math.min(...vals).toFixed(1)} · max ${Math.max(...vals).toFixed(1)}` : "waiting for readings"}
              </div>
            </div>
          );
        })}
      </div>
      <SerialMonitor sensors={sensors} />
      <p className="muted small" style={{ margin: 0, gridColumn: "1 / -1" }}>
        <span className="badge sim">SIMULATED</span> Physics-inspired values: a daily temperature cycle, humidity that falls as it
        gets hotter, and soil that dries out and gets irrigated. One simulated day lasts 2 real minutes.
      </p>
    </div>
  );
}
