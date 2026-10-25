"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { Mode } from "@/lib/api";
import { PIPE, SPECIAL, type VizState } from "@/lib/visualizer";
import { HELP, ICON, LOOK, currentStage } from "@/lib/stages";
import Rich from "@/components/Rich";

/** Right-hand panel: the current stage in big type, what is happening, an analogy, and what to look at. */
export default function Explain({ viz, mode, running }: { viz: VizState; mode: Mode; running: boolean }) {
  const cur = currentStage(viz.pipe);
  const stage = cur >= 0 ? PIPE[cur] : null;
  const n = viz.now;

  return (
    <section className="card explain">
      <AnimatePresence mode="wait">
        <motion.div key={stage?.id ?? "none"} className="explain-stage"
          initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.25 }}>
          {stage ? (
            <>
              <div className="explain-kicker">Stage {stage.n} of 7</div>
              <div className="explain-title"><span className="explain-icon">{ICON[stage.id]}</span>{stage.t}</div>
              <p className="explain-help">{HELP[stage.id]}</p>
              <p className="explain-look">👀 {LOOK[stage.id]}</p>
            </>
          ) : (
            <>
              <div className="explain-kicker">{running ? "Ready" : "Getting started"}</div>
              <div className="explain-title">{running ? "Send a reading" : "Press ▶ Start"}</div>
              <p className="explain-help">
                {running ? "The secure channel is up. Press 📨 Send a reading below and follow one message through all 7 stages."
                  : "Choose a security mode, press Start, and the first reading is sent automatically. Use Step-by-step to pause at every step."}
              </p>
            </>
          )}
        </motion.div>
      </AnimatePresence>

      <div className="explain-divider">What just happened</div>
      <AnimatePresence mode="wait">
        <motion.div key={n.id ?? "ready"} className="now"
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }}>
          <div className="lbl">{n.lbl}</div>
          <div className="title">{n.title}</div>
          <div className="text">{n.text}</div>
          {n.analogy && <div className="analogy"><b>Analogy:</b> {n.analogy}</div>}
        </motion.div>
      </AnimatePresence>

      {viz.history.length > 0 && (
        <details className="special">
          <summary>Earlier steps ({viz.history.length})</summary>
          <div className="history" style={{ marginTop: 6 }}>
            {viz.history.map((h, i) => <div key={h.id ?? i}><b>{h.lbl}:</b> {h.title}</div>)}
          </div>
        </details>
      )}
      <details className="special">
        <summary>What&apos;s special about this mode?</summary>
        <ul>{SPECIAL[mode].map((s) => <li key={s}><Rich text={s} /></li>)}</ul>
      </details>
    </section>
  );
}
