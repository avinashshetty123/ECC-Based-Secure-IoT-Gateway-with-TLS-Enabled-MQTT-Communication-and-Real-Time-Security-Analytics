"use client";

import { motion } from "framer-motion";
import { EcdheMixer, HandshakeTimeline, RecordAnatomy } from "@/components/learn/Explainers";

const CONCEPTS = [
  { t: "MQTT", d: "A lightweight publish/subscribe protocol. Devices publish to topics (ingest/dev-001); the broker forwards to subscribers. On its own it has no encryption.", a: "The postal system's rules: addresses (topics), a sorting office (broker) and mailboxes (subscriptions)." },
  { t: "Encryption", d: "Makes data unreadable without the key. Here TLS encrypts every MQTT packet with AES-128-GCM (a symmetric cipher).", a: "A sealed envelope." },
  { t: "Authentication", d: "Proving who you are. The broker proves itself with its certificate. Devices use a password (TLS mode) or their own certificate (mutual TLS).", a: "Showing an ID card." },
  { t: "Integrity", d: "Detecting tampering. Every TLS record carries a 16-byte GCM tag; one changed bit and the record is rejected. Plain MQTT has none.", a: "A tamper-evident seal." },
  { t: "ECC", d: "Elliptic-curve cryptography: public-key crypto with small keys. We use NIST P-256 (256-bit), about as strong as 3072-bit RSA.", a: "A lock-and-key system that is small but strong." },
  { t: "ECDSA", d: "An ECC signature algorithm. The CA signs certificates with it, and the broker/devices sign the handshake to prove they own their private key.", a: "A notary's stamp." },
  { t: "ECDHE", d: "Ephemeral ECC key agreement. Both sides derive the same secret without sending it; fresh keys per connection give forward secrecy. Here TLS 1.3 negotiated X25519.", a: "Mixing paint colours (see the animation above)." },
  { t: "TLS 1.3", d: "The protocol that combines all of the above: ECDHE for keys, ECDSA certificates for identity, AES-GCM for encrypted + authenticated records.", a: "The armoured van between the buildings." },
  { t: "ACL", d: "Topic-level authorisation in the broker: dev-001 may only write ingest/dev-001; only the gateway may write sensors/+/telemetry.", a: "Each resident's key only opens their own mailbox slot." },
  { t: "Gateway validation", d: "Application-level checks after TLS: schema, physical ranges and per-device sequence numbers (replay detection).", a: "Customs opening the suitcase after passport control." },
];

const DEFENSES = [
  ["Eavesdropping on the network", "TLS encryption (AES-GCM)", "Live demo: compare Plain vs TLS in the eavesdropper capture"],
  ["Wrong / missing password", "Broker authentication (password file)", "Scenarios: Wrong password, Anonymous client"],
  ["Client with no / rogue / expired / wrong-purpose certificate", "Mutual TLS certificate verification", "mTLS scenarios; Analytics: Bad client certificate"],
  ["Impostor broker", "Device verifies broker certificate + hostname", "Scenario: Impostor broker"],
  ["Device writing into another device's topic", "Broker topic ACL", "Scenario: Impersonate dev-002; Analytics: ACL publish denied"],
  ["Impossible / malformed sensor data", "Gateway schema + range validation", "Scenario: Invalid reading; fleet sends ~1 in 30 invalid"],
  ["Replaying a captured message", "Gateway per-device sequence check", "Scenario: Replay a captured message"],
  ["Tampering with bytes in transit", "TLS record authentication tag", "Learn: anatomy of an encrypted record"],
];

const fade = (i: number) => ({ initial: { opacity: 0, y: 12 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true }, transition: { delay: i * 0.04 } });

export default function LearnPage() {
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>How it works</h1>
          <p>The cryptography behind the gateway, explained with animations and everyday analogies. Everything here matches what you can observe on the Live demo.</p>
        </div>
      </div>

      <div className="callout" style={{ marginBottom: 16 }}>
        <b>What ECC does NOT do:</b> ECC does not encrypt the MQTT messages. ECDSA <i>authenticates</i> the parties and ECDHE
        <i> agrees a key</i>. The symmetric cipher TLS negotiates (AES-128-GCM here) encrypts the data using that key.
      </div>

      <div className="two" style={{ marginBottom: 16 }}>
        <motion.section className="card" {...fade(0)}>
          <h2 className="card-title">ECDHE key agreement as paint mixing</h2>
          <EcdheMixer />
        </motion.section>
        <motion.section className="card" {...fade(1)}>
          <h2 className="card-title">TLS 1.3 handshake, message by message</h2>
          <HandshakeTimeline />
        </motion.section>
      </div>

      <motion.section className="card" style={{ marginBottom: 16 }} {...fade(2)}>
        <h2 className="card-title">Anatomy of an encrypted MQTT record (hover the parts)</h2>
        <RecordAnatomy />
      </motion.section>

      <section className="card" style={{ marginBottom: 16 }}>
        <h2 className="card-title">Concepts</h2>
        <div className="concepts">
          {CONCEPTS.map((c, i) => (
            <motion.div key={c.t} className="concept" {...fade(i)} whileHover={{ y: -3, borderColor: "#3b82f6" }}>
              <h3>{c.t}</h3>
              <p>{c.d}</p>
              <p className="an">Analogy: {c.a}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="card" style={{ marginBottom: 16 }}>
        <h2 className="card-title">Which layer stops which attack</h2>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Threat</th><th>Stopped by</th><th>Where to see it</th></tr></thead>
            <tbody>
              {DEFENSES.map(([a, b, c], i) => (
                <motion.tr key={a} {...fade(i)}><td>{a}</td><td><b>{b}</b></td><td className="muted">{c}</td></motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="two">
        <section className="card">
          <h2 className="card-title">Defence in depth: the message path</h2>
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            <li><b>Device</b> verifies the broker (CA chain, hostname, ECDSA signature).</li>
            <li><b>TLS</b> encrypts and authenticates every byte (AES-GCM).</li>
            <li><b>Broker</b> authenticates the client (password or certificate) and enforces the topic ACL.</li>
            <li><b>Gateway</b> validates the content (schema, ranges, sequence/replay) and forwards only clean data.</li>
            <li><b>Collector</b> records readings, latency and every security event for the analytics.</li>
          </ol>
        </section>
        <section className="card">
          <h2 className="card-title">Honest limitations</h2>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>Certificates come from a local <b>demo CA</b> and are not publicly trusted; private keys are files on disk, not in a hardware module.</li>
            <li>All measurements are on <b>localhost</b>: they show the relative cost of TLS, not real network performance.</li>
            <li>Sensor values are <b>simulated</b>; there is no physical hardware.</li>
            <li>No certificate revocation (CRL/OCSP) and no broker high availability; this is a college demonstration, not a production system.</li>
          </ul>
        </section>
      </div>
    </main>
  );
}
