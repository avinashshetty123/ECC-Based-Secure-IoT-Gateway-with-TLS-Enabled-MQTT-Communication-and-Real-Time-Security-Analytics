"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { MODE_INFO, MODES, type Mode } from "@/lib/api";
import { useLive } from "@/lib/live";
import type { Speed } from "@/lib/useVisualizer";

/** One compact row: security mode · start/stop · speed · next (presenter). */
export default function Toolbar({ mode, onMode, speed, onSpeed, waiting, queued, onNext }: {
  mode: Mode; onMode: (m: Mode) => void; speed: Speed; onSpeed: (s: Speed) => void;
  waiting: boolean; queued: number; onNext: () => void;
}) {
  const { session, send } = useLive();
  const starting = session.state === "starting";

  const choose = (m: Mode) => {
    if (starting || m === mode) return;
    onMode(m);
    if (session.running) send("/api/start", { mode: m }); // switching mode restarts the system
  };

  // Presenter shortcut: → or N = next step
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.key === "ArrowRight" || ev.key.toLowerCase() === "n") && !(ev.target instanceof HTMLInputElement)) onNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onNext]);

  return (
    <div className="toolbar card">
      <div className="tb-group">
        <span className="tb-label">1 · Security mode</span>
        <div className="seg" role="group" aria-label="Security mode">
          {MODES.map((m) => (
            <button key={m} className={m} aria-pressed={m === mode} onClick={() => choose(m)} disabled={starting}>
              {MODE_INFO[m].label}
            </button>
          ))}
        </div>
      </div>
      <div className="tb-group">
        <span className="tb-label">2 · Run</span>
        <div className="row">
          <button className="btn primary" disabled={starting} onClick={() => send("/api/start", { mode })}>
            {starting ? "Starting…" : session.running ? "↻ Restart" : "▶ Start"}
          </button>
          <button className="btn danger" disabled={!session.running} onClick={() => send("/api/stop")}>■ Stop</button>
        </div>
      </div>
      <div className="tb-group">
        <span className="tb-label">3 · Pace</span>
        <div className="row">
          <div className="seg" role="group" aria-label="Animation speed">
            {(["step", "slow", "normal"] as Speed[]).map((s) => (
              <button key={s} aria-pressed={speed === s} onClick={() => onSpeed(s)}>
                {s === "step" ? "Step-by-step" : s === "slow" ? "Slow" : "Normal"}
              </button>
            ))}
          </div>
          {speed === "step" && (
            <motion.button className="btn primary" disabled={!waiting} onClick={onNext}
              animate={waiting ? { scale: [1, 1.06, 1] } : { scale: 1 }}
              transition={{ repeat: waiting ? Infinity : 0, duration: 1.2 }}>
              Next ▶{queued > 0 ? ` (${queued})` : ""}
            </motion.button>
          )}
        </div>
      </div>
      <div className="tb-mode">
        <span className={`tag ${mode}`}>{MODE_INFO[mode].tag}</span>
        <span className="small">{MODE_INFO[mode].text}</span>
      </div>
    </div>
  );
}
