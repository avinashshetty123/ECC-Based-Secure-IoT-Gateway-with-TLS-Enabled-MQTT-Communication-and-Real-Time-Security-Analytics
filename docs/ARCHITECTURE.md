# Phase 2 â€” Architecture and Design

> **Layout note:** all Python paths below (`app/`, `config/`, `scripts/`, `tests/`) now live under `backend/`; the web UI is the Next.js app in `frontend/`.

## 1. The system in plain language

Think of the system as a **post office with a security desk**:

| Real world | This project |
|---|---|
| Villagers writing letters | **Simulated IoT devices** (5â€“20 Python "sensors") |
| The post office sorting room | **Mosquitto MQTT broker**: it routes messages by *topic* |
| Security inspector at the counter | **Gateway**: it opens each letter, checks the format, and passes on only valid ones |
| Clerk who files everything in a cabinet | **Collector**: it stores readings and metrics in **SQLite** |
| Notice board in the town square | **Streamlit dashboard** |
| ID cards stamped by the town hall | **Certificates** issued by *our own local CA* |
| Armoured van between the buildings | **TLS**: an encrypted, tamper-evident tunnel |

Everything runs on one laptop (`127.0.0.1`). Nothing is exposed to the network.

## 2. Components and data flow

```
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   (1) publish raw JSON                    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚  Device simulator    â”‚ â”€â”€â”€ ingest/<device_id> â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¶â”‚                      â”‚
 â”‚  dev-001 â€¦ dev-020   â”‚                                           â”‚                      â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                           â”‚                      â”‚
                                                                    â”‚  Mosquitto broker    â”‚
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   (2) subscribe ingest/#                  â”‚  127.0.0.1 only      â”‚
 â”‚  Secure gateway      â”‚ â—€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ â”‚                      â”‚
 â”‚  â€¢ schema validation â”‚   (3) publish validated                   â”‚  mode = plain | tls  â”‚
 â”‚  â€¢ rate/seq checks   â”‚ â”€â”€â”€ sensors/<device_id>/telemetry â”€â”€â”€â”€â”€â”€â”€â–¶â”‚         | mtls       â”‚
 â”‚  â€¢ reject events     â”‚ â”€â”€â”€ gateway/events â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â–¶â”‚                      â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                                           â”‚  password_file + ACL â”‚
                                                                    â”‚  broker log â”€â”€â”€â”€â”€â”€â”€â” â”‚
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   (4) subscribe sensors/#, gateway/#      â”‚                    â”‚ â”‚
 â”‚  Collector           â”‚ â—€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ â”‚                    â”‚ â”‚
 â”‚  â€¢ latency calc      â”‚                                           â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”˜
 â”‚  â€¢ broker-log tailer â”‚ â—€â”€â”€ (5) parse auth / TLS failures from logs/mosquitto.log â”€â”€â”€â”€â”€â”˜
 â”‚  â€¢ psutil sampler    â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
            â”‚ (6) INSERT
            â–¼
 â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   (7) SELECT         â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â”‚  SQLite              â”‚ â—€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ â”‚  Streamlit dashboard  â”‚  http://localhost:8501
 â”‚  data/iot_gateway.db â”‚                      â”‚  Plotly charts        â”‚
 â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                      â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

Why does the gateway sit *behind* the broker instead of in front of it? MQTT clients only talk to brokers, so a
gateway that is itself an MQTT client is the standard pattern (the "edge processor"). Devices are allowed to write
**only** to `ingest/<their own id>`. Only the gateway may write to `sensors/#`. So a compromised device can't
inject "validated" data, and the ACL enforces that, not just our Python code.

## 3. How ECC, TLS, MQTT and the gateway fit together

| Term | What it is | Role here | Analogy |
|---|---|---|---|
| **MQTT** | Lightweight publish/subscribe messaging protocol | Carries the sensor JSON | The postal system's rules |
| **Encryption** | Makes data unreadable without a key | TLS encrypts every MQTT packet (AES-GCM / ChaCha20) | Sealed envelope |
| **Authentication** | Proving who you are | Broker proves identity with its cert. Clients use a password (TLS mode) or a cert (mTLS mode) | ID card |
| **Integrity** | Detecting tampering | TLS record MAC/AEAD tag; any modified byte means the record is rejected | Tamper-evident seal |
| **ECC** | Public-key cryptography based on elliptic curves; small keys, fast | Key type for all our certificates: **NIST P-256** (`prime256v1`) | A lock-and-key system that is small but strong |
| **ECDSA** | ECC *signature* algorithm | The CA signs certificates; the server and client prove they own their private key during the handshake | Notary's stamp |
| **ECDHE** | ECC *key agreement*, with a fresh key per session | Both sides derive a shared session key without sending it. "E" = ephemeral, so past sessions stay safe if a key leaks later (forward secrecy) | Two people mixing paint colours to get a shared secret colour |
| **TLS 1.2 / 1.3** | Protocol that combines all of the above | Wraps MQTT on ports 8883 / 8884 | The armoured van |

**What ECC does NOT do:** ECC does not encrypt the MQTT messages. ECDSA authenticates the parties and ECDHE
establishes a shared key. The *symmetric* cipher that TLS negotiates (e.g. AES-128-GCM) encrypts the data.
The `certificates/` content is **demo material from our own local CA**. It is not publicly trusted.

### TLS handshake (simplified, TLS 1.3 + mTLS)
1. Client â†’ broker: "Hello, I support TLS 1.3, these cipher suites, and an ECDHE key share."
2. Broker â†’ client: its ECDHE key share, its **certificate** (ECDSA P-256, signed by our CA) and a signature that proves it owns the key.
3. Client verifies: the cert chains to `ca.crt`, it isn't expired, and its **SAN matches `localhost`** (hostname check).
4. (mTLS only) Broker asks for the client's certificate; the client sends it and signs with its key; the broker verifies it against the CA.
5. Both sides derive the session keys from ECDHE. MQTT `CONNECT` now travels inside the encrypted tunnel.

## 4. Broker modes (one broker config per experiment)

| Mode | Port | Transport | Client authentication | Used for |
|---|---|---|---|---|
| `plain` | 1884 | TCP | username + password, ACL | Experiment A (baseline) |
| `tls` | 8883 | TLS 1.2+ | server cert verified by client; client uses username + password, ACL | Experiment B |
| `mtls` | 8884 | TLS 1.2+ | **client certificate required**; CN used as username, ACL | Experiment C + live demo |

Port 1884 is used instead of the standard 1883 so the project never clashes with the Windows "mosquitto"
service the installer creates. All three keep `allow_anonymous false` and bind to `localhost`, which means **both**
loopback addresses (`127.0.0.1` and `::1`). Binding only `127.0.0.1` made every connection wait ~2 s, because
Windows resolves `localhost` to `::1` first (measured: 2053 ms â†’ 8.9 ms). Only one mode runs at a time, so CPU and memory
measurements aren't mixed. The baseline still uses passwords and ACLs, so **the only variable between A and B is TLS**.
(Note: in plain mode the password crosses the wire unencrypted. That's acceptable only because it's localhost, and it's the
reason TLS exists.)

## 5. Identities (certificates)

| Identity | CN / username | Key | Purpose |
|---|---|---|---|
| Root CA | `IoT-Demo-Local-CA` | P-256 | Signs everything. Key never leaves `certificates/ca/` |
| Broker | `localhost` (SAN: `DNS:localhost`, `IP:127.0.0.1`) | P-256 | Server auth (EKU `serverAuth`) |
| Gateway | `gateway` | P-256 | Client auth (EKU `clientAuth`) |
| Collector/dashboard | `collector` | P-256 | Client auth |
| Devices | `dev-001` â€¦ `dev-020` | P-256 | Client auth |
| **Negative-test** | rogue CA + `rogue-client`; cert with wrong SAN; expired cert | P-256 | Must all be **rejected** |

## 6. Message schema (device â†’ gateway)

```json
{
  "schema_version": 1,
  "device_id": "dev-007",
  "seq": 1532,
  "ts_sent": 1761200000.123456,
  "ts_mono_ns": 17592377154700,
  "simulated": true,
  "readings": {
    "temperature_c": 27.4,
    "humidity_pct": 61.2,
    "soil_moisture_pct": 38.9
  }
}
```
Gateway rules: valid JSON; all fields present with correct types; `device_id` in the payload equals the topic's id;
values in physical ranges (temp âˆ’40â€¦85 Â°C, humidity/soil 0â€¦100 %); `seq` increases per device (to detect duplicates
and gaps); payload â‰¤ 1 KB. Rejected messages produce a `gateway/events` record with a reason. The payload itself is
never logged verbatim in full.

## 7. Metric definitions

| Metric | Exact definition |
|---|---|
| **E2E delivery latency** | `mono_ns(received) âˆ’ ts_mono_ns(sent)`, using `time.perf_counter_ns()` (QueryPerformanceCounter, 100 ns resolution, one counter shared by all processes on the machine). `time.time()` is **not** used: on Python 3.12/Windows its resolution is 15.6 ms (measured in Phase 3). Valid only because everything runs on one host. Includes both broker hops and the gateway. Excludes connection setup |
| **Connection establishment time** | From `connect()` call until `CONNACK` received (TCP + TLS handshake + MQTT auth). Measured in separate runs, *not* mixed into latency |
| **Throughput** | Messages received by the collector Ã· measurement-window seconds (after warm-up) |
| **Success rate** | unique `(device_id, seq)` received Ã· messages published in the window |
| **CPU / memory** | `psutil` sampled every 1 s for the broker PID and the Python processes; CPU % is normalised per core |
| **Rejected connections / TLS errors** | Counted from broker log lines (`not authorised`, `bad user name or password`, `certificate verify failed`, `tls`), plus client-side exceptions |

Localhost results show **relative** cost of TLS on this laptop. They don't predict real network latency.

## 8. SQLite schema (planned)

- `readings(id, device_id, seq, ts_sent, ts_received, latency_ms, temperature_c, humidity_pct, soil_moisture_pct, mode)`
- `security_events(id, ts, source, event_type, client_id, detail)` (source = broker_log | gateway | test)
- `connection_events(id, ts, client_id, mode, event, connect_ms)`
- `resource_samples(id, ts, process, cpu_pct, rss_mb, run_id)`
- `benchmark_runs(run_id, mode, repetition, devices, rate_hz, qos, warmup_s, duration_s, started_at, config_json)`
- `benchmark_results(run_id, sent, received, success_rate, throughput, lat_median_ms, lat_p95_ms, connect_median_ms, cpu_avg, rss_max_mb)`

## 9. File plan by phase

| Phase | Files |
|---|---|
| 3 â€“ MQTT prototype | `config/broker_plain.conf`, `config/acl.conf`, `scripts/create_passwords.ps1`, `scripts/start_broker.ps1`, `app/config.py`, `app/simulator/device.py`, `scripts/prototype_sub.py` |
| 4 â€“ ECC + TLS | `scripts/gen_certs.ps1`, `config/broker_tls.conf`, `config/broker_mtls.conf`, `app/mqtt/client_factory.py` (one place that builds plain/TLS/mTLS clients; verification always on), `scripts/verify_certs.ps1` |
| 5 â€“ Gateway + fleet | `app/gateway/schema.py`, `app/gateway/gateway.py`, `app/simulator/fleet.py`, `app/simulator/sensor_models.py`, `app/logging_setup.py` (redacts secrets) |
| 6 â€“ Data + dashboard | `app/analytics/db.py`, `app/analytics/collector.py`, `app/analytics/broker_log_tailer.py`, `app/dashboard/streamlit_app.py`, `scripts/run_demo.ps1` |
| 7 â€“ Benchmark + tests | `app/analytics/benchmark.py`, `scripts/run_benchmarks.ps1`, `config/benchmark.json`, `tests/test_schema.py`, `tests/test_tls_security.py`, `tests/test_acl.py`, `tests/test_reconnect.py`, `tests/test_no_secrets_in_git.py` |
| 8 â€“ Docs | `docs/architecture.png` (exported diagram), `reports/REPORT.md`, `docs/SETUP_WINDOWS.md`, `docs/TEST_EVIDENCE.md`, `docs/VIVA_GUIDE.md` |

## 10. Design decisions (for the viva)

- **No Docker**: it's too heavy for 8 GB RAM, and running Mosquitto natively is easier to explain.
- **One broker mode at a time**: gives clean, comparable measurements.
- **The gateway is an MQTT client**: this is the standard pattern, and the ACL stops devices from bypassing it.
- **Separate collector process**: the dashboard only reads SQLite, so refreshing the UI never affects measurements.
- **P-256 instead of Ed25519 certs**: it's widely supported by Mosquitto, Python `ssl` and OpenSSL, and it's a NIST standard.
- **Port 1884 + `localhost` binding**: see section 4.

## 11. Verified behaviour (measured, not assumed)

| Question | Observed result | Evidence |
|---|---|---|
| Does Mosquitto 2.1.2 honour `password_file` / `acl_file`? | Yes, through its `builtin-security` plugin | broker startup log; `tests/test_plain_broker.py` |
| Negotiated TLS (default) | **TLS 1.3**, `TLS_AES_128_GCM_SHA256`, server signature **ECDSA (P-256)**, key exchange **X25519** | `openssl s_client -brief`; `test_tls_valid_client_connects_with_tls13_and_ecdsa` |
| Negotiated TLS (forced 1.2) | `ECDHE-ECDSA-AES128-GCM-SHA256` | `test_tls12_also_works_with_ecdhe_ecdsa` |
| ECDHE curve | TLS 1.3 picks **X25519** (Curve25519) for the key exchange, not P-256. Both are elliptic curves. P-256 is used for certificates/signatures | `Server Temp Key: X25519` |
| `use_identity_as_username` | Works: the cert CN becomes the ACL username | `test_mtls_valid_device_connects_and_cn_is_username` |
| Denied SUBSCRIBE | Mosquitto replies "Granted QoS 1" but **delivers nothing**, because read rights are checked per message | `test_device_cannot_read_other_data` |
| Bad client certs (rogue CA, expired, wrong EKU, none) | All rejected during the TLS handshake | `test_mtls_bad_client_certificates_rejected`, broker log `certificate verify failed` |
