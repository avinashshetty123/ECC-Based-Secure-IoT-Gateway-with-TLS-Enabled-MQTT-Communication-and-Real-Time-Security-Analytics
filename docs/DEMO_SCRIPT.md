# Demonstration script (10–12 minutes)

**Before the session:** double-click `start.bat`, wait for http://localhost:3000, plug in the charger, close other apps.
Optional: open `docs/architecture.svg` in a second tab.

## 1. Architecture (1 min)
Show `docs/architecture.svg`: devices → broker (auth + ACL) → gateway (validation) → collector → SQLite → web app.
Point out the eavesdropper tap and the three ports (plain / TLS / mTLS).

## 2. The problem: plain MQTT (2 min) · Live demo page
1. Select **Plain TCP**, then **Start**.
2. Click **Send sensor reading**. Show the sensors lighting up and the packets moving.
3. Point at **Eavesdropper's latest capture**: "READABLE". The JSON, and in the CONNECT packet the password.
4. Pipeline stages 3–4 are amber: "SKIPPED: no TLS".

## 3. TLS with ECC (3 min)
1. Select **Mutual TLS** (it restarts automatically).
2. Click **Reconnect device** and narrate the handshake steps as they appear:
   ClientHello → ServerHello (X25519, TLS 1.3, AES-128-GCM) → encrypted certificates → verification → mTLS identity.
3. Click **Send sensor reading**. Journey card ② now shows ciphertext and the calculation
   "249 B = 227 B + 1 + **16 B auth tag** + 5". The eavesdropper says "ENCRYPTED: unreadable".

## 4. Attacks (3 min)
Click each one and point at the red burst, the narrator and the ✅ result:
- **Certificate from a rogue CA** and **Expired certificate**: rejected during the handshake.
- **Impostor broker**: the *device* refuses the broker.
- **Impersonate dev-002**: dropped by the broker ACL.
- **Invalid reading (humidity 250 %)** and **Replay**: rejected by the gateway.
Then scroll to **Logs**: show Mosquitto's own lines, e.g. `certificate verify failed` and `Denied PUBLISH`.

## 5. Analytics (1.5 min) · Analytics page
Click **Start 8-device fleet**. Wait 20 s, then show the throughput, median/p95 latency, the latency histogram,
security events by type (your attacks plus the fleet's deliberate invalid messages), CPU/RAM, sensor charts and CSV export.
Point out the SIMULATED vs MEASURED labels.

## 6. Results (1.5 min) · Benchmarks page
Read the key findings: TLS +0.3 ms median latency, +1.5 ms connection setup, 100 % delivery, 10/10 attack types
rejected. Show the CDF and the methodology table, and state the localhost limitation.

## If something goes wrong
- "Backend not running" screen: start `backend\scripts\start_backend.ps1`; the page reconnects by itself.
- `Port in use`: close any leftover benchmark/test window, then press Start again.
- Keep `docs/REPORT.md` open as a backup: it has the results tables.
