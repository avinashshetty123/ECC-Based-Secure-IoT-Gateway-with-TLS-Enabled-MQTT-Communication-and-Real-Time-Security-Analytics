/** Backend API access. The Python backend runs on 127.0.0.1:8600 (see backend/app/visualizer/server.py). */

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8600";

export type Mode = "plain" | "tls" | "mtls";
export const MODES: Mode[] = ["plain", "tls", "mtls"];

export interface FleetInfo {
  devices: number;
  rate: number;
  invalid_every: number;
}

export interface Session {
  mode: Mode | null;
  running: boolean;
  streaming: boolean;
  fleet: FleetInfo | null;
  broker_port: number | null;
  tap_port: number | null;
  state?: "starting" | "running" | "stopped" | "error";
  message?: string;
}

export interface Scenario {
  name: string;
  title: string;
  description: string;
  modes: Mode[];
  expect: "delivered" | "blocked";
  category: "normal" | "attack";
}

/** A live event from the backend's SSE stream. Fields depend on `kind`. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type LiveEvent = { id?: number; ts: number; kind: string; [key: string]: any };

export const EMPTY_SESSION: Session = {
  mode: null, running: false, streaming: false, fleet: null, broker_port: null, tap_port: null, state: "stopped",
};

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(API + path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return (await r.json()) as T;
}

export async function post(path: string, body?: object): Promise<{ ok: boolean; error?: string; offline?: boolean }> {
  try {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (r.ok) return { ok: true };
    const j = await r.json().catch(() => ({}));
    return { ok: false, error: j.error ?? r.statusText };
  } catch {
    return { ok: false, offline: true, error: "Backend not reachable" };
  }
}

export const MODE_INFO: Record<Mode, { tag: string; label: string; text: string }> = {
  plain: {
    tag: "PLAIN TCP",
    label: "Plain TCP",
    text: "Baseline: MQTT with no encryption. A username and password are still required, but they travel as readable text, and so does every sensor reading. Watch the eavesdropper read everything.",
  },
  tls: {
    tag: "TLS 1.3 + ECC",
    label: "TLS (ECC)",
    text: "The broker proves who it is with an ECDSA P-256 certificate from our local CA. Both sides agree a fresh key with ephemeral ECDHE, and every packet is encrypted with AES-GCM. Devices still log in with a password, but now inside the encrypted tunnel.",
  },
  mtls: {
    tag: "MUTUAL TLS",
    label: "Mutual TLS",
    text: "Both sides prove who they are with ECDSA P-256 certificates. The broker only lets in a device holding a certificate (and its private key) from our CA, and the certificate's name (CN) becomes the device's MQTT identity. No passwords at all.",
  },
};
