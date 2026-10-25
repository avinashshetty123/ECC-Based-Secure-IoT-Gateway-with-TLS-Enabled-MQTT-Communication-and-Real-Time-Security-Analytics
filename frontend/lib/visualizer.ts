/**
 * Visual state of the live demo, derived ONLY from real backend events.
 * `reduce` is a pure reducer: (state, action) -> new state.
 */
import type { LiveEvent, Mode } from "./api";

export type Status = "idle" | "active" | "done" | "fail" | "skip";
export type StageId = "sense" | "package" | "handshake" | "encrypt" | "transmit" | "authorize" | "deliver";
export type StepId = "tcp" | "ch" | "sh" | "ehs" | "verify" | "ccert" | "mqtt" | "data";
export type Lane = "c2s" | "s2c" | "gw" | "sense";
export type NodeId = "device" | "eve" | "broker" | "gateway" | "sensors";

export interface Packet { id: number; lane: Lane; label: string; cls: string }
export interface Burst { id: number; x: number; text: string; good: boolean }
export interface Narration { id?: number; lbl: string; title: string; text: string; analogy?: string | null }
export interface Verdict { id: number; title: string; outcome: string; expect: string; passed: boolean; detail: string; mode: string }
export interface Capture { kind: "readable" | "encrypted" | "handshake"; meta: string; data: string }
export interface JCard { sub: string; data: string; cls: string; math?: string; mathColor?: string }

export interface VizState {
  mode: Mode;
  nextId: number;
  pipe: Record<StageId, { status: Status; sub?: string }>;
  steps: Record<StepId, { status: Status; kv?: string[]; note?: string }>;
  connTitle: string;
  ehsCount: number;
  ehsNarrated: boolean;
  capture: Capture | null;
  captured: number;
  readable: number;
  packets: Packet[];
  bursts: Burst[];
  flash: Record<NodeId, { cls: string; n: number }>;
  device: { title: string; sub: string; attacker: boolean };
  sensors: { T: number[]; H: number[]; M: number[]; seq: number | null };
  journey: { j1: JCard; j2: JCard; j3: JCard };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pending: { topic: string; mqtt_bytes: number; ts: number; matched: boolean } | null;
  recentC2S: LiveEvent[];
  deviceChannel: { status: Status; sub?: string } | null;
  now: Narration;
  history: Narration[];
  verdicts: Verdict[];
  gwLatency: number | null;
  banner: string | null;
  runningScenario: string | null;
}

export type Action =
  | { type: "event"; e: LiveEvent }
  | { type: "packetDone"; id: number }
  | { type: "burstDone"; id: number }
  | { type: "setMode"; mode: Mode };

// ------------------------------------------------------------------ static content
export const PIPE: { id: StageId; n: number; t: string; s: string }[] = [
  { id: "sense", n: 1, t: "Sense", s: "sensors sampled" },
  { id: "package", n: 2, t: "Package", s: "JSON + seq + timestamp" },
  { id: "handshake", n: 3, t: "Secure channel", s: "TLS handshake (ECDHE + certs)" },
  { id: "encrypt", n: 4, t: "Encrypt", s: "AES-GCM record" },
  { id: "transmit", n: 5, t: "Transmit", s: "over TCP, past the tap" },
  { id: "authorize", n: 6, t: "Broker checks", s: "identity + topic ACL" },
  { id: "deliver", n: 7, t: "Gateway validates", s: "schema + range + replay check" },
];

export const STEPS: { id: StepId; t: string; d: string }[] = [
  { id: "tcp", t: "TCP connection", d: "Device opens a TCP socket. The eavesdropper sees addresses and ports." },
  { id: "ch", t: "ClientHello (plaintext)", d: "Device offers TLS versions and cipher suites, and sends its EPHEMERAL ECDHE public key." },
  { id: "sh", t: "ServerHello (plaintext)", d: "Broker picks the version and cipher and sends ITS ephemeral public key. Both sides now compute the SAME shared secret (ECDHE). The secret itself never crosses the wire." },
  { id: "ehs", t: "Encrypted handshake", d: "Broker Certificate + CertificateVerify (an ECDSA signature) + Finished. In TLS 1.3 these are already encrypted." },
  { id: "verify", t: "Device verifies the broker", d: "Chain → our CA, validity dates, hostname must match the SAN, and the signature must be valid." },
  { id: "ccert", t: "Broker verifies the device (mTLS)", d: "Device sends its own certificate + ECDSA signature. The CN becomes the MQTT username." },
  { id: "mqtt", t: "MQTT CONNECT / CONNACK", d: "Login and authorisation." },
  { id: "data", t: "Application data (AEAD)", d: "Every MQTT packet is encrypted AND authenticated." },
];

export const SPECIAL: Record<Mode, string[]> = {
  plain: [
    "This is the **baseline** used in Experiment A. Same broker, same access rules, no TLS.",
    "The eavesdropper can read the **password** and every **sensor value**. It could also change them, because nothing protects integrity.",
    "Access rules (ACLs) still work: authentication and authorisation are not the same as encryption.",
  ],
  tls: [
    "**ECC**: the broker certificate uses a 256-bit elliptic-curve key (NIST P-256), which gives about the same security as a 3072-bit RSA key (NIST SP 800-57) with far smaller keys.",
    "**ECDSA** signature: the broker proves it holds the private key behind its certificate, so an impostor broker is refused.",
    "**Forward secrecy**: every connection uses fresh, throw-away ECDHE (X25519) keys. Recorded traffic stays unreadable even if a long-term key leaks later.",
    "**AES-GCM** encrypts AND authenticates: the 16-byte tag in every record detects any tampering.",
    "**Hostname check**: the certificate must name `localhost`, so a valid certificate for another host is still rejected.",
  ],
  mtls: [
    "**Mutual authentication**: the device proves who it is with its own ECC certificate. A stolen password is useless without the private key.",
    "**Identity = certificate**: the CN (dev-001) becomes the MQTT username, so the broker ACL ties topics to a cryptographic identity.",
    "**Least privilege**: dev-001 may only publish to `ingest/dev-001`. Impersonating dev-002 is silently dropped.",
    "Rogue-CA, expired and wrong-purpose certificates are all rejected **during the handshake**, before any MQTT data is exchanged.",
    "**Forward secrecy + AES-GCM** as in TLS mode. In TLS 1.3 even the certificates travel encrypted.",
  ],
};

const READY: Narration = {
  lbl: "Ready",
  title: "Choose a mode and press Start",
  text: "The backend will start a real Mosquitto broker, put an eavesdropper on the wire, connect the gateway and device dev-001, and every step will be explained here as it happens.",
};

const EMPTY_J = (): VizState["journey"] => ({
  j1: { sub: "application layer, before TLS", data: "-", cls: "" },
  j2: { sub: "captured by the tap", data: "-", cls: "" },
  j3: { sub: "after TLS, ready to validate", data: "-", cls: "gw" },
});

function freshPipe(mode: Mode, keepChannel?: VizState["pipe"]["handshake"]): VizState["pipe"] {
  const p = Object.fromEntries(PIPE.map((x) => [x.id, { status: "idle" as Status }])) as VizState["pipe"];
  if (keepChannel) p.handshake = keepChannel;
  if (mode === "plain") {
    p.encrypt = { status: "skip", sub: "SKIPPED: no TLS, sent as plaintext" };
    if (!keepChannel) p.handshake = { status: "skip", sub: "no TLS: plain TCP only" };
  }
  return p;
}

function freshSteps(mode: Mode): VizState["steps"] {
  const s = Object.fromEntries(STEPS.map((x) => [x.id, { status: "idle" as Status }])) as VizState["steps"];
  if (mode === "plain") {
    for (const id of ["ch", "sh", "ehs", "verify", "ccert"] as StepId[]) s[id] = { status: "skip", note: "Not performed: no TLS in plain mode." };
    s.mqtt = { status: "idle", note: "Username and password are sent as CLEARTEXT inside the CONNECT packet." };
    s.data = { status: "idle", note: "Readings travel as readable JSON, with no confidentiality and no integrity protection." };
  } else if (mode === "tls") {
    s.ccert = { status: "skip", note: "Not required in TLS mode: the device logs in with a password inside the tunnel." };
  }
  return s;
}

export function initialState(mode: Mode = "mtls"): VizState {
  return {
    mode, nextId: 1, pipe: freshPipe(mode), steps: freshSteps(mode), connTitle: "No connection yet",
    ehsCount: 0, ehsNarrated: false, capture: null, captured: 0, readable: 0, packets: [], bursts: [],
    flash: { device: { cls: "", n: 0 }, eve: { cls: "", n: 0 }, broker: { cls: "", n: 0 }, gateway: { cls: "", n: 0 }, sensors: { cls: "", n: 0 } },
    device: { title: "dev-001", sub: "IoT device (simulated)", attacker: false },
    sensors: { T: [], H: [], M: [], seq: null }, journey: EMPTY_J(), pending: null, recentC2S: [], deviceChannel: null,
    now: READY, history: [], verdicts: [], gwLatency: null, banner: null, runningScenario: null,
  };
}

// ------------------------------------------------------------------ helpers
const isAttacker = (label: string) => label !== "dev-001";
const pretty = (o: unknown) => (typeof o === "string" ? o : JSON.stringify(o, null, 2));
const ms = (v: number | null | undefined, d = 1) => (typeof v === "number" ? v.toFixed(d) : "?");

function explainReject(reason: string) {
  const r = (reason || "").toLowerCase();
  if (r.includes("self-signed") || r.includes("unknown ca") || r.includes("certificate verification failed"))
    return "The DEVICE checked the broker's certificate against the CA it trusts and it did not match. It hung up before sending any data. This is server authentication protecting the device from impostors.";
  if (r.includes("not authori"))
    return "The broker checked the credentials and refused the login (CONNACK 'Not authorized'). In TLS mode even the wrong password travelled encrypted.";
  if (r.includes("dropped by broker"))
    return "The broker rejected the client certificate during the TLS handshake (Mosquitto logged e.g. 'certificate verify failed' or 'peer did not return a certificate'). The connection died before MQTT even started.";
  return reason;
}

function wireLabel(e: LiveEvent): string {
  if (e.layer === "mqtt") return e.rtype;
  if (e.layer === "raw") return "non-TLS bytes";
  if (e.rtype === "Handshake") return (e.handshake || []).map((h: { type: string }) => h.type).join("+") || "Handshake";
  if (e.rtype === "ChangeCipherSpec") return "CCS";
  if (e.rtype === "Alert") return "Alert";
  return `🔒 ${e.length} B`;
}
function wireClass(e: LiveEvent): string {
  if (e.layer === "mqtt") return "plain";
  if (e.layer === "raw" || e.rtype === "Alert") return "alert";
  if (e.rtype === "ApplicationData") return "enc";
  return "hs";
}

// ------------------------------------------------------------------ reducer
export function reduce(state: VizState, action: Action): VizState {
  if (action.type === "packetDone") return { ...state, packets: state.packets.filter((p) => p.id !== action.id) };
  if (action.type === "burstDone") return { ...state, bursts: state.bursts.filter((b) => b.id !== action.id) };
  if (action.type === "setMode") {
    return { ...state, mode: action.mode, pipe: freshPipe(action.mode), steps: freshSteps(action.mode), deviceChannel: null };
  }

  const e = action.e;
  // Work on a copy whose nested collections are new objects, so we can update them freely.
  const s: VizState = {
    ...state, pipe: { ...state.pipe }, steps: { ...state.steps }, flash: { ...state.flash },
    journey: { ...state.journey }, sensors: { ...state.sensors }, device: { ...state.device },
  };
  const id = () => s.nextId++;
  const pipe = (stage: StageId, status: Status, sub?: string) => { s.pipe[stage] = { status, sub: sub ?? s.pipe[stage]?.sub }; };
  const step = (st: StepId, status: Status, kv?: string[], note?: string) => {
    const prev = s.steps[st] || { status: "idle" };
    s.steps[st] = { status, kv: kv ?? prev.kv, note: note ?? prev.note };
  };
  const packet = (lane: Lane, label: string, cls: string) => { s.packets = [...s.packets, { id: id(), lane, label, cls }]; };
  const burst = (x: number, text: string, good: boolean) => { s.bursts = [...s.bursts, { id: id(), x, text, good }]; };
  const flash = (node: NodeId, cls: string) => { s.flash[node] = { cls, n: s.flash[node].n + 1 }; };
  const narrate = (n: Narration) => {
    if (s.now !== READY) s.history = [s.now, ...s.history].slice(0, 14);
    s.now = { ...n, id: id() };
  };
  const capture = (c: Capture) => {
    s.capture = c;
    s.captured += 1;
    if (c.kind === "readable") s.readable += 1;
    flash("eve", "flash-peek");
  };
  const enc = s.mode !== "plain";

  switch (e.kind) {
    // ---------------------------------------------------------- session lifecycle
    case "hello": {
      // Page opened (or reloaded) while the system is already running
      if (e.session?.running && s.now === READY) {
        s.now = { id: id(), lbl: "Ready", title: `${String(e.session.mode).toUpperCase()} system is running`, text: "Press 📨 Send a reading (or turn on auto-stream) to watch a message travel through all 7 stages, or try an attack from the Trigger panel." };
      }
      return s;
    }
    case "session": {
      if (e.mode && e.mode !== s.mode) {
        s.mode = e.mode;
      }
      if (e.state === "starting") {
        const fresh = initialState(s.mode);
        return {
          ...fresh, nextId: s.nextId, verdicts: s.verdicts,
          now: { lbl: "Starting", title: `Starting the ${String(e.mode).toUpperCase()} system…`, text: "Launching a real Mosquitto broker with this mode's configuration, putting the wire tap between the device and the broker, and connecting the gateway, the collector and dev-001." },
        };
      }
      if (e.state === "running" && e.mode && !e.fleet && s.now.lbl === "Starting") {
        narrate({ lbl: "Ready", title: `${String(e.mode).toUpperCase()} system is running`, text: `Broker on port ${e.broker_port}, eavesdropper tap on port ${e.tap_port}. Press "Send sensor reading", switch on auto-stream, or launch an attack.` });
      }
      return s;
    }

    // ---------------------------------------------------------- connections through the tap
    case "wire_conn": {
      if (e.event !== "open") return s;
      s.steps = freshSteps(s.mode);
      s.ehsCount = 0;
      s.ehsNarrated = false;
      s.connTitle = `Connection #${e.conn} · ${e.label}`;
      step("tcp", "done", [`connection #${e.conn}`, e.peer]);
      const attacker = isAttacker(e.label);
      s.device = { title: e.label.length > 20 ? e.label.slice(0, 19) + "…" : e.label, sub: attacker ? "UNTRUSTED client" : "IoT device (simulated)", attacker };
      if (enc) pipe("handshake", "active", `${attacker ? "attacker" : "device"} connecting…`);
      else pipe("handshake", "skip", "no TLS: plain TCP only");
      packet("c2s", "TCP connect", "tcp");
      narrate({
        lbl: "Stage 3 · Secure channel",
        title: attacker ? `An attacker connects: ${e.label}` : "Device opens a TCP connection",
        text: attacker ? "A hostile client tries to get in. Watch where the system stops it."
          : enc ? "A TCP connection is opened. Before any MQTT data is sent, TLS will build an encrypted, authenticated channel on top of it."
            : "A plain TCP connection is opened. No security layer is set up: whatever is sent next is readable.",
      });
      return s;
    }

    case "wire": {
      if (e.dir === "c2s") s.recentC2S = [...s.recentC2S, e].slice(-8);
      packet(e.dir === "c2s" ? "c2s" : "s2c", wireLabel(e), wireClass(e));
      const dirTxt = e.dir === "c2s" ? "device → broker" : "broker → device";
      if (e.layer === "mqtt") {
        capture({ kind: "readable", meta: `${dirTxt} · ${e.rtype} · ${e.length} B`, data: e.readable || e.hex });
      } else if (e.rtype === "Handshake") {
        const h = (e.handshake || [])[0] || {};
        const lines = [`${(e.handshake || []).map((x: { type: string }) => x.type).join(" + ")}  (${e.length} B)`];
        if (h.sni) lines.push(`SNI (server name, sent in clear): ${h.sni}`);
        if (h.versions_offered) lines.push(`versions offered: ${h.versions_offered.join(", ")}`);
        for (const k of h.key_shares || []) lines.push(`client ephemeral ${k.group} public key: ${k.public_key}`);
        if (h.version && h.cipher) lines.push(`server chose: ${h.version} · ${h.cipher}`);
        if (h.key_exchange) lines.push(`server ephemeral ${h.key_exchange} public key: ${h.server_public_key || ""}`);
        lines.push("Public keys are visible, but the shared secret computed from them is NOT.");
        capture({ kind: "handshake", meta: dirTxt, data: lines.join("\n") });
      } else {
        capture({ kind: e.encrypted ? "encrypted" : "handshake", meta: `${dirTxt} · ${e.rtype} · ${e.length} B`, data: `${e.header_hex || ""}  |  ${e.hex || ""}` });
      }

      if (e.layer === "tls" && e.rtype === "Handshake") {
        for (const h of e.handshake || []) {
          if (h.type === "ClientHello") {
            const kv: string[] = [];
            if (h.sni) kv.push("SNI " + h.sni);
            if (h.versions_offered) kv.push("offers " + h.versions_offered.join("/"));
            for (const k of h.key_shares || []) kv.push(`${k.group} pubkey ${k.public_key}`);
            step("tcp", "done");
            step("ch", "done", kv);
            pipe("handshake", "active", "ClientHello: offering TLS 1.3 + key share");
            const ks = (h.key_shares || [])[0] || {};
            narrate({
              lbl: "Stage 3 · Secure channel", title: "ClientHello: the device starts the TLS handshake",
              text: `The device offers TLS 1.3 and sends a freshly generated, throw-away ${ks.group || "ECDHE"} public key (${ks.key_bytes || "?"} bytes). This message is NOT encrypted yet: the eavesdropper can see it, including the server name "${h.sni || "-"}".`,
              analogy: "Like posting your half of a paint mix in public. Anyone can see the colour you sent, but not the secret colour you kept.",
            });
          }
          if (h.type === "ServerHello") {
            step("sh", "done", [h.version, h.cipher, `key exchange ${h.key_exchange || "?"}`, `server pubkey ${h.server_public_key || ""}`]);
            step("ehs", "active");
            pipe("handshake", "active", `ServerHello: ${h.version} · ${h.key_exchange} shared secret derived`);
            narrate({
              lbl: "Stage 3 · Secure channel", title: "ServerHello: both sides now share a secret",
              text: `The broker chose ${h.version} with ${h.cipher} and sent its own ephemeral ${h.key_exchange} public key. Each side mixes its private key with the other's public key (ECDHE) and gets the same secret, which never travels over the network. From the next record on, everything is encrypted.`,
              analogy: "Both people add their own secret colour to the other's public mix and end up with the identical final colour. An observer can't un-mix it.",
            });
          }
        }
      } else if (e.layer === "tls" && e.rtype === "ApplicationData" && s.steps.ehs.status === "active") {
        s.ehsCount += 1;
        step("ehs", "active", [`${s.ehsCount} encrypted record(s) so far`, "contents hidden from the eavesdropper"]);
        if (!s.ehsNarrated) {
          s.ehsNarrated = true;
          narrate({
            lbl: "Stage 3 · Secure channel", title: "Certificates are exchanged, already encrypted",
            text: s.mode === "mtls"
              ? "The broker sends its certificate plus an ECDSA signature, and asks for the device's certificate. The device answers with its own certificate and signature. All of this is inside encrypted records: the eavesdropper only sees their sizes."
              : "The broker sends its certificate plus an ECDSA signature proving it owns the matching private key. The device checks the chain up to our CA, the dates, and that the name matches \"localhost\".",
            analogy: "Showing a stamped ID card through a sealed envelope. The guard can check it, but passers-by can't read it.",
          });
        }
      } else if (e.layer === "mqtt" && e.rtype === "CONNECT") {
        step("tcp", "done");
        const f = e.fields || {};
        step("mqtt", "active", [`username ${f.username || "-"}`, f.password_exposed ? "password READABLE on the wire" : "no password"]);
        narrate({
          lbl: "Stage 3 · Login", title: "MQTT CONNECT sent in CLEARTEXT",
          text: `The device logs in as "${f.username || "-"}". With no TLS, the username and password are plain bytes on the wire, and the eavesdropper just captured them (shown masked here).`,
          analogy: "Shouting your PIN across a crowded room.",
        });
      }
      matchJourney(s);
      return s;
    }

    case "connect": {
      if (e.ok) {
        if (enc) {
          if (s.steps.ehs.status === "active") step("ehs", "done");
          const p = e.peer_cert || {};
          step("verify", "done", [`subject CN=${p.subject_cn}`, `issuer ${p.issuer_cn}`, p.key, p.signature, `SAN ${(p.san || []).join(", ")}`, `hostname "${e.hostname_checked}" ✓`, `expires ${p.not_after}`]);
          if (s.mode === "mtls") {
            const o = e.own_cert || {};
            step("ccert", "done", [`presented CN=${o.subject_cn}`, o.key, o.signature, `→ MQTT username "${o.subject_cn}"`]);
          }
          pipe("handshake", "done", `${e.tls_version} · ${e.cipher} · ${ms(e.connect_ms)} ms`);
        } else {
          pipe("handshake", "skip", `plain TCP · ${ms(e.connect_ms)} ms · password exposed`);
        }
        step("mqtt", "done", ["CONNACK accepted", `connect time ${ms(e.connect_ms)} ms (TCP${enc ? " + TLS" : ""} + MQTT)`]);
        step("data", enc ? "done" : "fail", enc ? [e.cipher, e.tls_version] : ["NO encryption", "NO integrity protection"]);
        if (!isAttacker(e.actor)) {
          s.deviceChannel = { ...s.pipe.handshake };
          s.device = { title: "dev-001", sub: "IoT device (simulated)", attacker: false };
          const p = e.peer_cert || {}, o = e.own_cert || {};
          narrate({
            lbl: "Stage 3 · Secure channel",
            title: enc ? "Secure channel established ✓" : "Connected, but nothing is protected",
            text: !enc ? `Logged in after ${ms(e.connect_ms)} ms. The broker checked the password, but everyone on the wire saw it.`
              : s.mode === "mtls" ? `Both sides are verified. The device checked the broker's certificate (CN=${p.subject_cn}, ${p.key}, ${p.signature}, issued by "${p.issuer_cn}"). The broker checked the device's certificate (CN=${o.subject_cn}), which became its MQTT username. ${e.tls_version} + ${e.cipher}, ready in ${ms(e.connect_ms)} ms.`
                : `The device verified the broker's certificate (CN=${p.subject_cn}, ${p.key}, ${p.signature}, hostname "${e.hostname_checked}" matched), then logged in with its password INSIDE the tunnel. ${e.tls_version} + ${e.cipher}, ready in ${ms(e.connect_ms)} ms.`,
            analogy: enc ? "A sealed, tamper-evident armoured van now connects the two buildings." : null,
          });
        }
      } else {
        const deviceSide = String(e.reason || "").startsWith("certificate verification failed");
        const failAt: StepId = deviceSide ? "verify" : s.mode === "mtls" ? "ccert" : "mqtt";
        if (enc && s.steps.ehs.status === "active") step("ehs", "done");
        step(failAt, "fail", undefined, (deviceSide ? "Device REFUSED the broker: " : "Broker REFUSED the client: ") + e.reason);
        if (deviceSide || s.mode === "mtls") pipe("handshake", "fail", deviceSide ? "device refused the broker's certificate" : "client certificate rejected");
        else pipe("authorize", "fail", "login refused (Not authorized)");
        burst(deviceSide ? 100 : 640, deviceSide ? "✕ device refused broker" : "✕ REJECTED", false);
        flash(deviceSide ? "device" : "broker", "flash-bad");
        narrate({
          lbl: deviceSide ? "Blocked by the device" : "Blocked by the broker", title: `Rejected: ${e.actor}`, text: explainReject(e.reason),
          analogy: deviceSide ? "The courier checks the receiving office's official seal, sees it's fake, and keeps the parcel."
            : "The guard checks the ID card, sees it's not issued by the town hall (or has expired), and shuts the gate.",
        });
      }
      return s;
    }

    // ---------------------------------------------------------- a reading leaves dev-001
    case "app_publish": {
      s.pending = { topic: e.topic, mqtt_bytes: e.mqtt_bytes, ts: e.ts, matched: false };
      s.pipe = freshPipe(s.mode, s.deviceChannel ?? undefined);
      s.device = { title: "dev-001", sub: "IoT device (simulated)", attacker: false };
      const r = (e.payload || {}).readings || {};
      if (!e.spoofed && !e.note && typeof r.temperature_c === "number") {
        s.sensors = {
          T: [...s.sensors.T, r.temperature_c].slice(-40), H: [...s.sensors.H, r.humidity_pct].slice(-40),
          M: [...s.sensors.M, r.soil_moisture_pct].slice(-40), seq: e.payload.seq,
        };
        flash("sensors", "sensor-ping");
      }
      pipe("sense", "done", `T ${r.temperature_c}°C · H ${r.humidity_pct}% · S ${r.soil_moisture_pct}%`);
      pipe("package", "done", `${e.payload_bytes} B JSON → ${e.mqtt_bytes} B MQTT PUBLISH`);
      if (enc) pipe("encrypt", "active", "TLS encrypting with AES-GCM…");
      s.journey = {
        j1: { sub: `${e.actor} → ${e.topic} · ${e.payload_bytes} B JSON · MQTT ${e.mqtt_bytes} B${e.spoofed ? " · SPOOFED device_id!" : ""}${e.note ? " · " + String(e.note).toUpperCase() : ""}`, data: pretty(e.payload), cls: enc ? "" : "plain" },
        j2: { sub: "captured by the tap", data: "waiting for the tap…", cls: "" },
        j3: { sub: "after TLS, ready to validate", data: "waiting for the gateway…", cls: "gw" },
      };
      packet("sense", "JSON", "data");
      flash("device", "flash-glow");
      if (e.note) {
        narrate({
          lbl: "Attack · Stage 1-2", title: `dev-001 sends a bad message: ${e.note}`,
          text: `This comes from the REAL, authenticated dev-001 on its OWN topic (${e.topic}), so TLS and the broker ACL both let it through. Only the gateway's application-level checks can catch it: schema and physical ranges, plus the per-device sequence number (seq ${e.payload.seq}) that detects replays.`,
          analogy: "A genuine employee with a valid badge hands in a form full of nonsense. The badge check passes, so the form itself must be checked.",
        });
      } else if (e.spoofed) {
        narrate({
          lbl: "Attack · Stage 1-2", title: "dev-001 sends a FAKE reading for dev-002",
          text: `The authenticated dev-001 builds a message claiming device_id "dev-002" and publishes it to ${e.topic}. Will the broker let one device write into another device's topic?`,
          analogy: "Signing a letter with your neighbour's name.",
        });
      } else {
        narrate({
          lbl: "Stage 1-2 · Sense & package", title: `Sensors sampled (reading #${e.payload.seq})`,
          text: `Temperature ${r.temperature_c} °C, humidity ${r.humidity_pct} %, soil moisture ${r.soil_moisture_pct} %. Packed into ${e.payload_bytes} bytes of JSON with a sequence number (detects loss and replays) and a timestamp (for latency), then wrapped in a ${e.mqtt_bytes}-byte MQTT PUBLISH for ${e.topic}.`,
        });
      }
      matchJourney(s);
      return s;
    }

    case "broker_log": {
      const line: string = e.line || "";
      if (/Received PUBLISH from/.test(line) && /'ingest\//.test(line)) {
        const topic = (line.match(/'(ingest\/[^']+)'/) || [])[1] || "";
        pipe("authorize", "done", `ACL ✓ allowed to write ${topic}`);
        if (s.pipe.deliver.status === "idle") pipe("deliver", "active", "gateway validating…");
      } else if (/Denied PUBLISH/.test(line)) {
        const topic = (line.match(/'([^']+)'/) || [])[1] || "";
        pipe("authorize", "fail", `ACL ✕ not allowed to write ${topic}`);
        pipe("deliver", "fail", "dropped, never reached the gateway");
        burst(640, "✕ ACL: topic denied", false);
        flash("broker", "flash-bad");
        s.journey = { ...s.journey, j3: { sub: "nothing arrived", data: `✕ Dropped by the broker's ACL: this identity may not write to ${topic}.`, cls: "bad" } };
        narrate({
          lbl: "Stage 6 · Blocked by ACL", title: `Broker DENIED the publish to ${topic}`,
          text: "The client is authenticated, but its identity only grants write access to its own topic. The broker silently dropped the message. In MQTT 3.1.1 the client still receives a PUBACK, so an attacker cannot even tell whether it worked.",
          analogy: "A resident with a valid key tries to post into a neighbour's mailbox. The slot is locked to them.",
        });
      }
      return s;
    }

    case "gateway_rx": {
      packet("gw", enc ? "🔒" : "PUB", enc ? "enc" : "plain");
      flash("gateway", "flash-glow");
      if (s.pipe.authorize.status !== "done") pipe("authorize", "done", "ACL ✓");
      pipe("deliver", "done", `valid ✓ → ${e.forwarded_to || "telemetry"} · ${ms(e.latency_ms, 2)} ms`);
      s.gwLatency = e.latency_ms ?? null;
      s.journey = { ...s.journey, j3: { sub: `${e.topic} · ${e.bytes} B · end-to-end latency ${ms(e.latency_ms, 3)} ms`, data: pretty(e.payload), cls: "gw" } };
      narrate({
        lbl: "Stage 6-7 · Broker checks & gateway validates", title: "Gateway validated and forwarded the reading ✓",
        text: `The broker ${enc ? "decrypted the record, " : ""}checked its access list (this device may write to ${e.topic}), and re-sent it to the gateway over the gateway's ${enc ? "own separate TLS connection (different session keys)" : "plain TCP connection"}. The gateway checked the schema, the physical ranges and the sequence number, then published the clean reading to ${e.forwarded_to || "sensors/<id>/telemetry"}. Measured latency device → gateway: ${ms(e.latency_ms, 3)} ms.`,
      });
      return s;
    }

    case "gateway_reject": {
      packet("gw", enc ? "🔒" : "PUB", enc ? "enc" : "plain");
      flash("gateway", "flash-bad");
      burst(900, "✕ gateway rejected", false);
      if (s.pipe.authorize.status !== "done") pipe("authorize", "done", "ACL ✓ (own topic)");
      pipe("deliver", "fail", "REJECTED: " + e.reason);
      s.journey = { ...s.journey, j3: { sub: `${e.topic} · ${e.size} B · reported on gateway/events`, data: `✕ Rejected by the gateway, NOT forwarded:\n\n${e.reason}`, cls: "bad" } };
      narrate({
        lbl: "Stage 7 · Blocked by the gateway", title: "Gateway REJECTED the message",
        text: `Reason: ${e.reason}. TLS proved who sent it and the ACL proved it was the device's own topic, but the CONTENT failed validation. It is not forwarded; a security event goes to gateway/events and appears on the Analytics page.`,
        analogy: "Passport control lets the traveller in, but customs still opens the suitcase.",
      });
      return s;
    }

    case "scenario": {
      s.runningScenario = e.name;
      s.banner = `▶ ${e.title}: ${e.description}  (expected: ${e.expect})`;
      if (e.category === "attack") narrate({ lbl: "Attack started", title: e.title, text: e.description });
      return s;
    }

    case "verdict": {
      s.runningScenario = null;
      s.verdicts = [{ id: id(), title: e.title, outcome: e.outcome, expect: e.expect, passed: e.passed, detail: e.detail, mode: e.mode }, ...s.verdicts].slice(0, 40);
      if (e.outcome === "delivered" && e.expect === "delivered") burst(900, "✓ delivered", true);
      return s;
    }

    default:
      return s;
  }
}

/** Pair the plaintext the device just sent with the record the eavesdropper captured. */
function matchJourney(s: VizState) {
  const p = s.pending;
  if (!p || p.matched) return;
  for (const r of s.recentC2S) {
    if (r.ts < p.ts - 0.05) continue;
    let math = "";
    if (r.layer === "mqtt" && r.rtype === "PUBLISH" && (r.fields || {}).topic === p.topic) {
      math = `${r.length} B on the wire = the same ${p.mqtt_bytes} B MQTT packet, NOT encrypted`;
    } else if (r.layer === "tls" && r.rtype === "ApplicationData" && r.length === p.mqtt_bytes + 22) {
      math = `${r.length} B record = ${p.mqtt_bytes} B MQTT packet + 1 B content type + 16 B AES-GCM auth tag + 5 B record header ✓`;
    } else continue;
    const enc = r.layer === "tls";
    s.pending = { ...p, matched: true };
    s.journey = {
      ...s.journey,
      j2: {
        sub: enc ? "TLS ApplicationData record: ciphertext" : "MQTT PUBLISH: readable by anyone on the path",
        data: enc ? `${r.header_hex}  |  ${r.hex}` : r.readable || "", cls: enc ? "enc" : "plain", math, mathColor: enc ? "var(--enc)" : "var(--plain)",
      },
    };
    if (enc) s.pipe.encrypt = { status: "done", sub: `${p.mqtt_bytes} B → ${r.length} B record (+16 B auth tag)` };
    s.pipe.transmit = { status: "done", sub: enc ? "eavesdropper saw only ciphertext" : "eavesdropper READ the full message" };
    if (s.pipe.authorize.status === "idle") s.pipe.authorize = { status: "active", sub: "broker checking ACL…" };
    const n: Narration = enc
      ? { lbl: "Stage 4-5 · Encrypt & transmit", title: "Encrypted with AES-GCM and sent", text: `TLS turned the ${p.mqtt_bytes}-byte MQTT packet into a ${r.length}-byte record: +16 bytes AES-GCM authentication tag (integrity: any change is detected), +1 byte hidden content type, +5 bytes record header. The eavesdropper captured only random-looking bytes. Even the topic name is hidden.`, analogy: "The letter is locked in a box with a tamper seal. Outsiders can only weigh the box." }
      : { lbl: "Stage 5 · Transmit (unprotected)", title: "Sent as readable plaintext", text: `The ${r.length}-byte packet crossed the wire exactly as written. The eavesdropper read the topic and every sensor value, and could have altered them without anyone noticing.`, analogy: "A postcard: every postman along the route can read and edit it." };
    s.history = [s.now, ...s.history].slice(0, 14);
    s.now = { ...n, id: s.nextId++ };
    return;
  }
}

/** How long to wait after showing an event before showing the next one (ms). */
export function paceFor(e: LiveEvent): number {
  switch (e.kind) {
    case "wire": return 330;
    case "wire_conn": return 300;
    case "app_publish": return 450;
    case "connect": case "gateway_rx": case "gateway_reject": case "verdict": return 300;
    case "broker_log": return /PUBLISH/.test(e.line || "") ? 150 : 0;
    case "scenario": case "session": return 80;
    default: return 0;
  }
}
