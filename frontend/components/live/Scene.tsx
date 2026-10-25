"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Mode, Session } from "@/lib/api";
import { PIPE, type Action, type Lane, type StageId, type VizState } from "@/lib/visualizer";
import { ICON, currentStage } from "@/lib/stages";
import { FieldArt } from "./FieldDevice";

/* ---------------------------------------------------------------- geometry (viewBox 1400 x 380) */
const WIRE_Y = 152;
const LANES: Record<Lane, { x0: number; x1: number; y: number; dur: number }> = {
  sense: { x0: 470, x1: 548, y: 140, dur: 0.5 },
  c2s: { x0: 548, x1: 935, y: 138, dur: 1.2 },
  s2c: { x0: 935, x1: 548, y: 168, dur: 1.2 },
  gw: { x0: 1134, x1: 1192, y: WIRE_Y, dur: 0.6 },
};
type Zone = "field" | "network" | "broker" | "gateway";
const ZONE: Record<Zone, { x: number; y: number; width: number; height: number; label: string }> = {
  field: { x: 4, y: 28, width: 532, height: 250, label: "Field device" },
  network: { x: 546, y: 6, width: 386, height: 214, label: "Network" },
  broker: { x: 932, y: 76, width: 206, height: 150, label: "Broker" },
  gateway: { x: 1186, y: 76, width: 210, height: 272, label: "Gateway" },
};
const STAGE_ZONE: Record<StageId, Zone> = {
  sense: "field", package: "field", handshake: "network", encrypt: "network", transmit: "network",
  authorize: "broker", deliver: "gateway",
};

function NodeBox({ x, y, w, h, flash, title, lines, attacker }: {
  x: number; y: number; w: number; h: number; flash: { cls: string; n: number }; title: string; lines: string[]; attacker?: boolean;
}) {
  return (
    <g>
      <rect key={flash.n} className={`node-box ${flash.cls} ${attacker ? "node-attacker" : ""}`} x={x} y={y} width={w} height={h} rx="14" />
      <text className="node-title" x={x + w / 2} y={y + 32} textAnchor="middle">{title}</text>
      {lines.map((l, i) => (
        <text key={i} className="node-sub" x={x + w / 2} y={y + 58 + i * 22} textAnchor="middle">{l}</text>
      ))}
    </g>
  );
}

export default function Scene({ viz, mode, session, dispatch, slow = 1 }: {
  viz: VizState; mode: Mode; session: Session; dispatch: (a: Action) => void; slow?: number;
}) {
  const enc = mode !== "plain";
  const tun = !session.running ? "off" : enc ? "enc" : "plain";
  const fl = viz.flash;
  const cur = currentStage(viz.pipe);
  const stage = cur >= 0 ? PIPE[cur] : null;
  const zone = stage ? ZONE[STAGE_ZONE[stage.id]] : null;
  const failed = stage ? viz.pipe[stage.id]?.status === "fail" : false;

  // Show the newest verdict on the scene for a few seconds
  const latest = viz.verdicts[0];
  const [shown, setShown] = useState<number | null>(null);
  useEffect(() => {
    if (!latest) return;
    setShown(latest.id);
    const t = setTimeout(() => setShown(null), 6000);
    return () => clearTimeout(t);
  }, [latest]);

  return (
    <section className="card scene">
      <div className="scene-wrap">
        <svg className="stage-svg" viewBox="0 0 1400 380" role="img"
          aria-label="The whole path: sensors and ESP32, the network with an eavesdropper, the MQTT broker, the gateway and the database">
          {/* spotlight on the part of the system the current stage is about */}
          {zone && (
            <motion.g initial={false} animate={{ x: zone.x, y: zone.y }} transition={{ type: "spring", stiffness: 90, damping: 18 }}>
              <motion.rect className={`spotlight ${failed ? "bad" : ""}`} rx="16" x={0} y={0}
                initial={false} animate={{ width: zone.width, height: zone.height }} transition={{ type: "spring", stiffness: 90, damping: 18 }} />
              <g transform="translate(12,-10)">
                <rect className={`spot-tag ${failed ? "bad" : ""}`} width={Math.max(150, (stage!.t.length + 14) * 8)} height="22" rx="11" />
                <text className="spot-tag-text" x="10" y="15">{ICON[stage!.id]} Now: {stage!.n}. {stage!.t}</text>
              </g>
            </motion.g>
          )}

          {/* ① field device */}
          <g transform="translate(10,40) scale(0.74)">
            <FieldArt sensors={viz.sensors} flash={fl} mode={mode} />
          </g>

          <AnimatePresence>
            {viz.device.attacker && (
              <motion.g initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
                <rect x="330" y="232" width="200" height="40" rx="10" fill="#3b1420" stroke="#ef4444" strokeWidth="2" />
                <text x="430" y="249" textAnchor="middle" fill="#fecaca" fontSize="13" fontWeight="700">🦹 attacker connecting</text>
                <text x="430" y="265" textAnchor="middle" fill="#fca5a5" fontSize="11">{viz.device.title}</text>
              </motion.g>
            )}
          </AnimatePresence>

          {/* ② network with eavesdropper */}
          <line className="wire" x1="528" y1={WIRE_Y} x2="940" y2={WIRE_Y} />
          <rect className={`tunnel ${tun}`} x="556" y="120" width="372" height="64" rx="14" />
          <text className={`tlabel ${tun}`} x="566" y="110">
            {!session.running ? "not connected" : enc ? "🔒 TLS tunnel · ECDHE + AES-GCM" : "⚠ PLAINTEXT · readable by anyone"}
          </text>
          <line x1="735" y1="80" x2="735" y2={WIRE_Y} stroke="#f5a524" strokeWidth="1.5" strokeDasharray="4 5" className={session.running ? "flow-dash" : ""} />
          <circle cx="735" cy={WIRE_Y} r="7" fill="#f5a524" />
          <NodeBox x={645} y={8} w={180} h={72} flash={fl.eve} title="👁 Eavesdropper" lines={[]} />
          <text className="node-sub" x="735" y="66" textAnchor="middle">copies every byte</text>

          {/* ③ broker */}
          <NodeBox x={940} y={86} w={190} h={132} flash={fl.broker} title="MQTT broker"
            lines={[session.broker_port ? `port ${session.broker_port}` : "stopped", enc ? "📜 cert CN=localhost" : "no certificate", "login + topic ACL"]} />

          {/* ④ gateway + database */}
          <line className="wire" x1="1130" y1={WIRE_Y} x2="1195" y2={WIRE_Y} />
          <rect className={`tunnel ${tun}`} x="1140" y="130" width="50" height="44" rx="12" />
          <NodeBox x={1195} y={86} w={200} h={132} flash={fl.gateway} title="Secure gateway"
            lines={["schema · range · replay", viz.gwLatency != null ? `latency ${viz.gwLatency.toFixed(2)} ms` : "validates content"]} />
          <path d="M1295 218 V 260" stroke="#3b4a6b" strokeWidth="3" markerEnd="url(#arrowDown)" />
          <defs>
            <marker id="arrowDown" viewBox="0 0 10 10" refX="5" refY="8" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M0,0 L10,0 L5,10 z" fill="#3b4a6b" />
            </marker>
          </defs>
          <g>
            <ellipse cx="1295" cy="272" rx="58" ry="10" fill="#1e293b" stroke="#475569" />
            <rect x="1237" y="272" width="116" height="52" fill="#1e293b" stroke="none" />
            <path d="M1237 272 V 324 M1353 272 V 324" stroke="#475569" />
            <ellipse cx="1295" cy="324" rx="58" ry="10" fill="#1e293b" stroke="#475569" />
            <text className="node-sub" x="1295" y="298" textAnchor="middle">SQLite</text>
            <text className="node-sub" x="1295" y="314" textAnchor="middle">→ Analytics page</text>
          </g>

          {/* zone captions */}
          {([["① Sensors + ESP32", 270, 304], ["② Network (tapped)", 740, 244], ["③ Broker", 1035, 244], ["④ Gateway → database", 1295, 368]] as const).map(([t, x, y]) => (
            <text key={t} className="zone-caption" x={x} y={y} textAnchor="middle">{t}</text>
          ))}

          {/* packets in flight */}
          {viz.packets.map((p) => {
            const L = LANES[p.lane];
            const w = Math.max(46, p.label.length * 8.2 + 22);
            return (
              <motion.g key={p.id} className={`pkt ${p.cls}`}
                initial={{ x: L.x0, y: L.y, opacity: 0.2 }} animate={{ x: L.x1, y: L.y, opacity: 1 }}
                transition={{ duration: L.dur * Math.min(slow, 2), ease: "easeInOut" }}
                onAnimationComplete={() => dispatch({ type: "packetDone", id: p.id })}>
                <rect x={-w / 2} y={-13} width={w} height={26} rx={7} />
                <text x={0} y={5} textAnchor="middle">{p.label}</text>
              </motion.g>
            );
          })}

          {/* red/green bursts, positioned in scene coordinates */}
          <AnimatePresence>
            {viz.bursts.map((b) => {
              const x = b.x < 300 ? 470 : b.x < 800 ? 1035 : 1295;
              return (
                <motion.text key={b.id} className={`burst-text ${b.good ? "good" : "bad"}`} x={x} textAnchor="middle"
                  initial={{ opacity: 0, y: 88 }} animate={{ opacity: [0, 1, 1, 0], y: [88, 78, 78, 70] }}
                  transition={{ duration: 2.4, times: [0, 0.15, 0.75, 1] }}
                  onAnimationComplete={() => dispatch({ type: "burstDone", id: b.id })}>
                  {b.text}
                </motion.text>
              );
            })}
          </AnimatePresence>
        </svg>

        <AnimatePresence>
          {latest && shown === latest.id && (
            <motion.div className={`scene-verdict ${latest.passed ? "pass" : "fail"}`}
              initial={{ opacity: 0, y: -10, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -10 }}>
              <b>{latest.passed ? "✅" : "❌"} {latest.title}: {latest.outcome.toUpperCase()}</b>
              <span>{latest.detail}</span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* what the eavesdropper sees */}
      <div className="capture">
        <div className="head">
          <b style={{ color: "var(--text)" }}>👁 Eavesdropper&apos;s latest capture</b>
          {viz.capture && (
            <span className={`verdict-tag ${viz.capture.kind}`}>
              {viz.capture.kind === "readable" ? "READABLE" : viz.capture.kind === "encrypted" ? "ENCRYPTED: unreadable" : "HANDSHAKE"}
            </span>
          )}
          <span>{viz.capture?.meta}</span>
          <span className="spacer" />
          <span>{viz.captured} captured · {viz.readable} readable</span>
        </div>
        <pre>{viz.capture?.data ?? "Nothing captured yet."}</pre>
      </div>
      <div className="legend">
        <span><i style={{ background: "#e2e8f0" }} />sensor JSON</span>
        <span><i style={{ background: "var(--plain)" }} />readable plaintext</span>
        <span><i style={{ background: "var(--hs)" }} />TLS handshake</span>
        <span><i style={{ background: "var(--enc)" }} />encrypted record</span>
        <span><i style={{ background: "var(--bad)" }} />alert / rejected</span>
        <span><i style={{ background: "#94a3b8" }} />TCP connect</span>
      </div>
    </section>
  );
}
