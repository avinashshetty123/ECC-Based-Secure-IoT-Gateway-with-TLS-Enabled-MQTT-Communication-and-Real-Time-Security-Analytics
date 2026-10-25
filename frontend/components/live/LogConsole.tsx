"use client";

import { useEffect, useRef, useState } from "react";
import { useLiveEvents } from "@/lib/live";
import type { LiveEvent } from "@/lib/api";

const CATS = ["WIRE", "APP", "BROKER", "SECURITY", "VERDICT", "SYS", "ERROR"] as const;
type Cat = (typeof CATS)[number];
interface Line { id: number; ts: number; cat: Cat; text: string }

function toLine(e: LiveEvent): [Cat, string] | null {
  switch (e.kind) {
    case "wire":
      return ["WIRE", `${e.label} ${e.dir === "c2s" ? "→" : "←"} ${String(e.layer).toUpperCase()} ${e.rtype}${e.handshake ? " [" + e.handshake.map((h: { type: string }) => h.type).join(", ") + "]" : ""} ${e.length} B${e.readable ? "  " + String(e.readable).slice(0, 160) : e.encrypted ? "  (ciphertext)" : ""}`];
    case "wire_conn":
      return ["WIRE", e.event === "open" ? `TCP connection #${e.conn} opened by ${e.label} (${e.peer})` : `connection #${e.conn} (${e.label}) closed`];
    case "connect":
      return e.ok ? ["APP", `${e.actor}: connected in ${Number(e.connect_ms).toFixed(1)} ms ${e.tls_version ?? "(plain TCP)"} ${e.cipher ?? ""}`]
        : ["SECURITY", `${e.actor}: REJECTED: ${e.reason}`];
    case "app_publish":
      return ["APP", `${e.actor} publishes to ${e.topic} (${e.payload_bytes} B payload)${e.spoofed ? " - pretending to be dev-002" : ""}${e.note ? " - " + e.note : ""}`];
    case "gateway_rx":
      return ["APP", `gateway accepted ${e.topic} (${e.bytes} B), latency ${e.latency_ms != null ? Number(e.latency_ms).toFixed(3) + " ms" : "n/a"}`];
    case "gateway_reject":
      return ["SECURITY", `gateway rejected message on ${e.topic}: ${e.reason}`];
    case "gateway_event":
      return ["APP", `gateway: ${e.type} ${e.device_id ?? ""}`];
    case "broker_log":
      return [e.level === "security" ? "SECURITY" : "BROKER", e.line];
    case "scenario":
      return ["SYS", `scenario "${e.title}" started (expected: ${e.expect})`];
    case "verdict":
      return ["VERDICT", `${e.passed ? "PASS" : "FAIL"} ${e.title}: ${e.outcome} (expected ${e.expect}) - ${e.detail}`];
    case "session":
      return [e.state === "error" ? "ERROR" : "SYS", `session ${e.state}${e.mode ? ` (${e.mode})` : ""}${e.message ? ": " + e.message : ""}`];
    case "info":
      return ["SYS", e.message];
    case "error":
      return ["ERROR", e.message];
    default:
      return null;
  }
}

export default function LogConsole() {
  const [lines, setLines] = useState<Line[]>([]);
  const [enabled, setEnabled] = useState<Set<Cat>>(new Set(CATS));
  const box = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const seq = useRef(0);

  useLiveEvents((e) => {
    const l = toLine(e);
    if (!l) return;
    const line: Line = { id: ++seq.current, ts: e.ts ?? Date.now() / 1000, cat: l[0], text: l[1] };
    setLines((prev) => [...prev.slice(-599), line]);
  });

  useEffect(() => {
    if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines]);

  const toggle = (c: Cat) => setEnabled((s) => {
    const n = new Set(s);
    if (n.has(c)) n.delete(c); else n.add(c);
    return n;
  });

  return (
    <div>
      <div className="filters">
        <span className="badge real">wire · app · Mosquitto&apos;s own log</span>
        {CATS.map((c) => (
          <button key={c} className={`chip c-${c}`} aria-pressed={enabled.has(c)} onClick={() => toggle(c)}>{c}</button>
        ))}
        <span className="spacer" />
        <button className="btn ghost small" style={{ padding: "2px 10px" }} onClick={() => setLines([])}>Clear</button>
      </div>
      <div className="log" ref={box} role="log"
        onScroll={(ev) => {
          const el = ev.currentTarget;
          stick.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
        }}>
        {lines.filter((l) => enabled.has(l.cat)).map((l) => {
          const d = new Date(l.ts * 1000);
          return (
            <div key={l.id}>
              <span className="time">{d.toTimeString().slice(0, 8)}.{String(d.getMilliseconds()).padStart(3, "0")}  </span>
              <span className={`cat c-${l.cat}`}>{l.cat}</span> {l.text}
            </div>
          );
        })}
      </div>
    </div>
  );
}
