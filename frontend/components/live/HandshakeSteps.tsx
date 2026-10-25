"use client";

import { motion } from "framer-motion";
import { STEPS, type VizState } from "@/lib/visualizer";

export default function HandshakeSteps({ viz }: { viz: VizState }) {
  return (
    <div>
      <div className="muted small" style={{ marginBottom: 8 }}>{viz.connTitle} · observed live from the wire tap</div>
      <ol className="steps">
        {STEPS.map((s) => {
          const st = viz.steps[s.id] ?? { status: "idle" };
          return (
            <motion.li key={s.id} className={st.status} layout transition={{ duration: 0.2 }}>
              <div className="st">{s.t}</div>
              <div className="sd">{st.note ?? s.d}</div>
              {st.kv && st.kv.length > 0 && (
                <div className="kv">
                  {st.kv.filter(Boolean).map((k, i) => (
                    <motion.span key={k + i} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }}>{k}</motion.span>
                  ))}
                </div>
              )}
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
