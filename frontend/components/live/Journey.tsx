"use client";

import { motion } from "framer-motion";
import type { JCard, VizState } from "@/lib/visualizer";

function Card({ title, c }: { title: string; c: JCard }) {
  return (
    <motion.div className={`jcard ${c.cls}`} key={c.data.slice(0, 40)}
      initial={{ opacity: 0.4, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
      <h3>{title}</h3>
      <div className="sub">{c.sub}</div>
      <pre>{c.data}</pre>
      {c.math && <div className="math" style={{ color: c.mathColor }}>{c.math}</div>}
    </motion.div>
  );
}

/** Plaintext at the device → what the attacker sees on the wire → what the gateway receives. */
export default function Journey({ journey }: { journey: VizState["journey"] }) {
  return (
    <div className="journey">
      <Card title="① At the device: plaintext" c={journey.j1} />
      <div className="arrow">➜</div>
      <Card title="② On the wire: what an attacker sees" c={journey.j2} />
      <div className="arrow">➜</div>
      <Card title="③ At the gateway: decrypted + validated" c={journey.j3} />
    </div>
  );
}
