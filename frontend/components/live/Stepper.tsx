"use client";

import { motion } from "framer-motion";
import { PIPE, type VizState } from "@/lib/visualizer";
import { ICON, currentStage } from "@/lib/stages";

/** The 7 stages as one progress line; a 📨 token sits on the stage the message is in. */
export default function Stepper({ pipe }: { pipe: VizState["pipe"] }) {
  const cur = currentStage(pipe);
  const progress = cur < 0 ? 0 : cur / (PIPE.length - 1);
  return (
    <div className="stepper card">
      <div className="stepper-track">
        <div className="stepper-line" />
        <motion.div className="stepper-fill" animate={{ scaleX: progress }} transition={{ duration: 0.6, ease: "easeInOut" }} />
      </div>
      <div className="stepper-items">
        {PIPE.map((p, i) => {
          const st = pipe[p.id] ?? { status: "idle" };
          return (
            <div key={p.id} className={`step ${st.status} ${i === cur ? "current" : ""}`}>
              <motion.div className="step-dot" animate={i === cur ? { scale: [1, 1.15, 1] } : { scale: 1 }}
                transition={{ repeat: i === cur ? Infinity : 0, duration: 1.4 }}>
                {st.status === "done" ? "✓" : st.status === "fail" ? "✕" : ICON[p.id]}
                {i === cur && (
                  <motion.span layoutId="step-token" className="step-token" transition={{ type: "spring", stiffness: 140, damping: 18 }}>📨</motion.span>
                )}
              </motion.div>
              <div className="step-title">{p.n}. {p.t}</div>
              <div className="step-sub">{st.sub ?? p.s}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
