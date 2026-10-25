import { PIPE, type StageId, type VizState } from "./visualizer";

export const ICON: Record<StageId, string> = {
  sense: "🌡️", package: "📦", handshake: "🤝", encrypt: "🔐", transmit: "📡", authorize: "🛂", deliver: "✅",
};

/** One-sentence, beginner-friendly meaning of each stage. */
export const HELP: Record<StageId, string> = {
  sense: "The device reads its three sensors: temperature, air humidity and soil moisture.",
  package: "The readings become a small JSON message with a sequence number (spots lost or replayed messages) and a timestamp (measures delay).",
  handshake: "Before any data is sent, device and broker build a secure channel: they agree a secret key (ECDHE) and check each other's certificates (ECDSA).",
  encrypt: "TLS locks the message with AES-GCM: outsiders can't read it, and a 16-byte tag reveals any change.",
  transmit: "The bytes cross the network. Our eavesdropper copies everything that passes. See what it can (or can't) read.",
  authorize: "The broker unlocks the message, checks who sent it, and whether that device may write to this topic (ACL).",
  deliver: "The gateway checks the content itself (format, realistic values, not a replay). Only clean data is stored and shown.",
};

/** What to look at on screen during each stage. */
export const LOOK: Record<StageId, string> = {
  sense: "Pulses run from the sensors along the wires into the ESP32.",
  package: "A JSON packet leaves the ESP32. Its exact text is in the 'Journey' tab.",
  handshake: "Purple handshake records go back and forth; only the first two are readable.",
  encrypt: "The green 🔒 packet is the encrypted reading. Its size gives away the 16-byte tag.",
  transmit: "Watch the eavesdropper box: READABLE (plain) or ENCRYPTED (TLS).",
  authorize: "The broker box flashes; a red ✕ here means the ACL blocked it.",
  deliver: "The gateway flashes green (accepted) or red (rejected), then the data goes to the database.",
};

/** Index of the stage the message is in right now (-1 = none yet). */
export function currentStage(pipe: VizState["pipe"]): number {
  let cur = -1;
  PIPE.forEach((p, i) => { if (pipe[p.id]?.status === "active") cur = i; });
  if (cur >= 0) return cur;
  PIPE.forEach((p, i) => { if (["done", "fail"].includes(pipe[p.id]?.status)) cur = i; });
  return cur;
}
