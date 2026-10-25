"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { useLive } from "@/lib/live";
import type { Mode, Scenario } from "@/lib/api";

/** Attacks grouped by the defence that stops them. */
const GROUPS: { title: string; icon: string; defence: string; names: string[] }[] = [
  { title: "Identity", icon: "🪪", defence: "stopped by passwords & certificates", names: ["wrong_password", "anonymous", "no_client_cert", "rogue_cert", "expired_cert", "wrong_purpose_cert"] },
  { title: "Impostor", icon: "🎭", defence: "stopped by the device checking the broker", names: ["untrusted_broker"] },
  { title: "Permissions", icon: "🚧", defence: "stopped by the broker's topic ACL", names: ["impersonate"] },
  { title: "Bad data", icon: "🧪", defence: "stopped by the gateway's checks", names: ["invalid_reading", "replay"] },
];

export default function Actions({ mode, runningScenario }: { mode: Mode; runningScenario: string | null }) {
  const { session, scenarios, send } = useLive();
  const [fleetSize, setFleetSize] = useState(8);
  const live = session.running && session.state !== "starting";
  const byName = Object.fromEntries(scenarios.map((s) => [s.name, s])) as Record<string, Scenario>;

  return (
    <section className="actions">
      <div className="card actions-normal">
        <h2 className="card-title">Normal operation</h2>
        <button className="btn primary big" disabled={!live} onClick={() => send("/api/trigger", { name: "send_reading" })}>
          📨 Send a reading
        </button>
        <button className="btn big" disabled={!live} onClick={() => send("/api/trigger", { name: "reconnect" })}>
          🤝 Reconnect (replay the handshake)
        </button>
        <label className="switch">
          <input type="checkbox" checked={session.streaming} disabled={!live}
            onChange={(e) => send("/api/stream", { enabled: e.target.checked, interval: 2 })} />
          <span className="track" /> Auto-send a reading every 2 s
        </label>
        <div className="row">
          <label className="switch">
            <input type="checkbox" checked={!!session.fleet} disabled={!live}
              onChange={(e) => send("/api/fleet", { enabled: e.target.checked, devices: fleetSize, rate: 1, invalid_every: 30 })} />
            <span className="track" /> Fleet of
          </label>
          <input type="number" min={1} max={19} value={fleetSize} style={{ width: 58 }}
            onChange={(e) => setFleetSize(Math.max(1, Math.min(19, Number(e.target.value) || 1)))} />
          <span className="small">extra devices</span>
        </div>
        <p className="muted small" style={{ margin: 0 }}>The fleet feeds the Analytics page; it isn&apos;t animated here.</p>
      </div>

      <div className="card actions-attacks">
        <h2 className="card-title">Try an attack <span className="badge bad">each should be blocked</span></h2>
        <div className="attack-groups">
          {GROUPS.map((g) => (
            <div key={g.title} className="attack-group">
              <div className="attack-group-head"><span>{g.icon}</span><b>{g.title}</b><span className="muted small">{g.defence}</span></div>
              {g.names.map((name) => {
                const sc = byName[name];
                if (!sc) return null;
                const applies = sc.modes.includes(mode);
                return (
                  <motion.button key={name} className={`attack ${runningScenario === name ? "running" : ""}`}
                    disabled={!live || !applies} whileHover={live && applies ? { y: -2 } : undefined}
                    title={sc.description} onClick={() => send("/api/trigger", { name })}>
                    <span>{sc.title}</span>
                    {!applies && <span className="small muted">{sc.modes.join("/")} only</span>}
                  </motion.button>
                );
              })}
            </div>
          ))}
        </div>
        {!session.running && <p className="muted small" style={{ marginBottom: 0 }}>Press ▶ Start first.</p>}
      </div>
    </section>
  );
}
