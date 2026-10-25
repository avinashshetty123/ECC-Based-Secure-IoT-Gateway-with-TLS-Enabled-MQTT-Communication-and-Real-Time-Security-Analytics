"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { VizState } from "@/lib/visualizer";
import Journey from "./Journey";
import HandshakeSteps from "./HandshakeSteps";
import SensorPanel from "./SensorPanel";
import LogConsole from "./LogConsole";

type Tab = "journey" | "handshake" | "sensors" | "results" | "logs";

/** Secondary detail, one tab at a time. All tabs stay mounted so the logs keep collecting. */
export default function DetailTabs({ viz }: { viz: VizState }) {
  const [tab, setTab] = useState<Tab>("journey");
  const passed = viz.verdicts.filter((v) => v.passed).length;
  const TABS: { id: Tab; label: string; badge?: string }[] = [
    { id: "journey", label: "📨 Journey of a reading" },
    { id: "handshake", label: "🤝 TLS handshake" },
    { id: "sensors", label: "🌱 Sensors" },
    { id: "results", label: "🛡️ Attack results", badge: viz.verdicts.length ? `${passed}/${viz.verdicts.length}` : undefined },
    { id: "logs", label: "📜 Logs" },
  ];

  return (
    <section className="card details">
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
            {t.badge && <span className="badge real" style={{ marginLeft: 6 }}>{t.badge}</span>}
            {tab === t.id && <motion.span layoutId="tab-underline" className="tab-underline" />}
          </button>
        ))}
      </div>

      <div className="tab-body">
        <div hidden={tab !== "journey"}>
          <p className="muted small" style={{ marginTop: 0 }}>The same reading in three places. Compare what the device sent, what an attacker on the network captured, and what the gateway received.</p>
          <Journey journey={viz.journey} />
        </div>
        <div hidden={tab !== "handshake"}><HandshakeSteps viz={viz} /></div>
        <div hidden={tab !== "sensors"}><SensorPanel sensors={viz.sensors} /></div>
        <div hidden={tab !== "results"}>
          <div className="verdicts">
            {viz.verdicts.length === 0 && <div className="empty">No scenarios run yet. Try an attack above.</div>}
            <AnimatePresence initial={false}>
              {viz.verdicts.map((v) => (
                <motion.div key={v.id} className={`v ${v.passed ? "pass" : "fail"}`} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
                  <b>{v.passed ? "✅" : "❌"} {v.title}: {v.outcome.toUpperCase()} ({v.mode})</b>
                  <small>expected {v.expect} · {v.detail}</small>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
        <div hidden={tab !== "logs"}><LogConsole /></div>
      </div>
    </section>
  );
}
