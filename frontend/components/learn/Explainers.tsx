"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/* ------------------------------------------------------------------ ECDHE as paint mixing */
const MIX_STEPS = [
  { t: "1. Agree on a public base colour", d: "Both sides know the same public starting point. In ECDHE this is the curve and its generator point (X25519 or P-256), which is public and standard." },
  { t: "2. Each side picks a secret colour", d: "The device and the broker each generate a random private key for THIS connection only (ephemeral). It never leaves their memory." },
  { t: "3. Mix and send the mixture", d: "Each side mixes base + secret and sends the mixture: its ephemeral PUBLIC key, inside ClientHello / ServerHello. The eavesdropper sees both mixtures." },
  { t: "4. Add your secret to the other's mixture", d: "Each side adds its own secret colour to the mixture it received. Both end up with the SAME final colour: the shared secret." },
  { t: "5. The secret never travelled", d: "Un-mixing paint is practically impossible; for elliptic curves this is the hard 'discrete logarithm' problem. TLS turns the shared secret into AES-GCM session keys. The private keys are thrown away afterwards, which gives forward secrecy." },
];

function Blob({ color, label, show = true, size = 54 }: { color: string; label: string; show?: boolean; size?: number }) {
  return (
    <div style={{ textAlign: "center", width: 96 }}>
      <AnimatePresence>
        {show && (
          <motion.div initial={{ scale: 0, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0, opacity: 0 }}
            style={{ width: size, height: size, borderRadius: "50%", background: color, margin: "0 auto", boxShadow: `0 0 18px ${color}66` }} />
        )}
      </AnimatePresence>
      <div className="small muted" style={{ marginTop: 4, minHeight: 32 }}>{show ? label : ""}</div>
    </div>
  );
}

export function EcdheMixer() {
  const [step, setStep] = useState(0);
  const [auto, setAuto] = useState(true);
  useEffect(() => {
    if (!auto) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % MIX_STEPS.length), 3200);
    return () => clearTimeout(t);
  }, [step, auto]);
  const BASE = "#facc15", A = "#ef4444", B = "#3b82f6", MIXA = "#f97316", MIXB = "#84cc16", FINAL = "#a16207";
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 150px 1fr", alignItems: "center", gap: 10, minHeight: 230 }}>
        <div className="row" style={{ justifyContent: "center", flexDirection: "column" }}>
          <b>Device</b>
          <div className="row" style={{ justifyContent: "center" }}>
            <Blob color={BASE} label="public base" />
            <Blob color={A} label="secret (private key)" show={step >= 1} />
          </div>
          <Blob color={FINAL} label="shared secret ✓" show={step >= 3} size={64} />
        </div>
        <div style={{ textAlign: "center" }}>
          <div className="small muted">public wire 👁</div>
          <AnimatePresence>
            {step >= 2 && (
              <>
                <motion.div initial={{ x: -120, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.8 }}
                  style={{ width: 34, height: 34, borderRadius: "50%", background: MIXA, margin: "8px auto" }} title="device public key" />
                <motion.div initial={{ x: 120, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ duration: 0.8, delay: 0.2 }}
                  style={{ width: 34, height: 34, borderRadius: "50%", background: MIXB, margin: "8px auto" }} title="broker public key" />
                <div className="small" style={{ color: "var(--plain)" }}>the eavesdropper sees these mixtures</div>
              </>
            )}
          </AnimatePresence>
        </div>
        <div className="row" style={{ justifyContent: "center", flexDirection: "column" }}>
          <b>Broker</b>
          <div className="row" style={{ justifyContent: "center" }}>
            <Blob color={BASE} label="public base" />
            <Blob color={B} label="secret (private key)" show={step >= 1} />
          </div>
          <Blob color={FINAL} label="shared secret ✓" show={step >= 3} size={64} />
        </div>
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={step} className="now" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          <div className="title">{MIX_STEPS[step].t}</div>
          <div className="text">{MIX_STEPS[step].d}</div>
        </motion.div>
      </AnimatePresence>
      <div className="row">
        <button className="btn" onClick={() => { setAuto(false); setStep((s) => Math.max(0, s - 1)); }}>◀ Back</button>
        <button className="btn" onClick={() => { setAuto(false); setStep((s) => (s + 1) % MIX_STEPS.length); }}>Next ▶</button>
        <label className="switch"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /><span className="track" />auto-play</label>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ TLS 1.3 handshake sequence */
interface Msg { from: "D" | "B"; label: string; enc: boolean; note: string; mtlsOnly?: boolean }
const HS: Msg[] = [
  { from: "D", label: "ClientHello + key share", enc: false, note: "TLS versions, cipher suites, SNI 'localhost' and the device's ephemeral X25519 public key. Readable by anyone." },
  { from: "B", label: "ServerHello + key share", enc: false, note: "Chosen version (TLS 1.3) and cipher (AES-128-GCM) plus the broker's ephemeral public key. Both sides now derive the handshake keys." },
  { from: "B", label: "EncryptedExtensions", enc: true, note: "From here on everything is encrypted with keys derived from ECDHE." },
  { from: "B", label: "CertificateRequest", enc: true, note: "Mutual TLS only: the broker asks the device for its certificate.", mtlsOnly: true },
  { from: "B", label: "Certificate (P-256)", enc: true, note: "The broker's certificate: CN=localhost, EC P-256 key, signed by our demo CA with ECDSA-SHA256." },
  { from: "B", label: "CertificateVerify (ECDSA)", enc: true, note: "A signature over the whole handshake so far, made with the broker's PRIVATE key. Proves it owns the certificate." },
  { from: "B", label: "Finished", enc: true, note: "A MAC over the transcript: detects any tampering with earlier handshake messages." },
  { from: "D", label: "Certificate + CertificateVerify", enc: true, note: "Mutual TLS only: the device proves its identity the same way. CN=dev-001 becomes its MQTT username.", mtlsOnly: true },
  { from: "D", label: "Finished", enc: true, note: "The device has verified the chain (our CA), the dates and the hostname. The handshake is complete." },
  { from: "D", label: "MQTT CONNECT / PUBLISH", enc: true, note: "Application data: every MQTT packet is an AES-GCM record with a 16-byte authentication tag." },
];

export function HandshakeTimeline() {
  const [mtls, setMtls] = useState(true);
  const msgs = HS.filter((m) => mtls || !m.mtlsOnly);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (n >= msgs.length) return;
    const t = setTimeout(() => setN((x) => x + 1), 1100);
    return () => clearTimeout(t);
  }, [n, msgs.length]);
  const sel = msgs[Math.max(0, Math.min(n, msgs.length) - 1)];
  return (
    <div>
      <div className="row" style={{ marginBottom: 10 }}>
        <label className="switch"><input type="checkbox" checked={mtls} onChange={(e) => { setMtls(e.target.checked); setN(0); }} /><span className="track" />mutual TLS</label>
        <button className="btn" onClick={() => setN(0)}>↺ Replay</button>
        <span className="small muted"><span style={{ color: "var(--hs)" }}>■</span> plaintext &nbsp; <span style={{ color: "var(--enc)" }}>■</span> encrypted</span>
      </div>
      <div className="seq">
        <div className="seq-row"><div className="seq-actor">📟 Device</div><div /><div className="seq-actor">🖥 Broker</div></div>
        {msgs.slice(0, n).map((m, i) => (
          <motion.div key={m.label + i} className="seq-row" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div />
            <div className="seq-msg">
              <motion.div className="seq-line" style={{ background: m.enc ? "var(--enc)" : "var(--hs)", transformOrigin: m.from === "D" ? "left" : "right" }}
                initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.6 }} />
              <div style={m.from === "D"
                ? { position: "absolute", top: 9, right: -2, color: m.enc ? "var(--enc)" : "var(--hs)" }
                : { position: "absolute", top: 9, left: -2, color: m.enc ? "var(--enc)" : "var(--hs)" }}>
                {m.from === "D" ? "▶" : "◀"}
              </div>
              <span className="seq-label">{m.enc ? "🔒 " : ""}{m.label}</span>
            </div>
            <div />
          </motion.div>
        ))}
      </div>
      {n > 0 && sel && (
        <motion.div key={sel.label} className="now" style={{ marginTop: 10 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <div className="title">{sel.enc ? "🔒 " : ""}{sel.label}</div>
          <div className="text">{sel.note}</div>
        </motion.div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ anatomy of an encrypted record */
export function RecordAnatomy() {
  const parts = [
    { w: 5, label: "header 5 B", color: "#64748b", note: "type 0x17 'application data', version 0x0303, length: the only readable part" },
    { w: 227, label: "encrypted MQTT PUBLISH (227 B)", color: "#22c55e", note: "topic + JSON reading, AES-128-GCM ciphertext: looks like random bytes" },
    { w: 1, label: "1 B", color: "#a78bfa", note: "real content type, hidden inside the encryption" },
    { w: 16, label: "auth tag 16 B", color: "#f59e0b", note: "GCM authentication tag: change one bit and the record is rejected (integrity)" },
  ];
  const total = parts.reduce((a, p) => a + p.w, 0);
  const [hover, setHover] = useState(1);
  return (
    <div>
      <div style={{ display: "flex", height: 46, borderRadius: 10, overflow: "hidden", border: "1px solid var(--line)" }}>
        {parts.map((p, i) => (
          <motion.div key={i} onMouseEnter={() => setHover(i)}
            initial={{ flexGrow: 0 }} animate={{ flexGrow: Math.max(p.w / total, 0.06) }} transition={{ duration: 0.8, delay: i * 0.15 }}
            style={{ background: p.color, display: "grid", placeItems: "center", color: "#0a0f1e", fontWeight: 700, fontSize: 11.5, cursor: "pointer",
              outline: hover === i ? "2px solid white" : "none", outlineOffset: -2, whiteSpace: "nowrap", overflow: "hidden" }}>
            {p.label}
          </motion.div>
        ))}
      </div>
      <p style={{ marginBottom: 0 }}><b>{parts[hover].label}:</b> {parts[hover].note}</p>
      <p className="muted small">
        Measured in this project: a 227-byte MQTT packet became a 249-byte TLS record (227 + 1 + 16 + 5). The Live demo shows this
        calculation for every reading.
      </p>
    </div>
  );
}
