# Project Report
## ECC-Based Secure IoT Gateway with TLS-Enabled MQTT Communication and Real-Time Security Analytics

Subject: IoT Data Analytics and Visualization · Budget: ₹0 (free and open-source tools only) · Platform: Windows 11 laptop

---

### 1. Abstract
IoT devices often send sensor data over MQTT without encryption. This project builds a complete, locally running IoT
system: simulated agricultural sensors, an Eclipse Mosquitto broker, a validating gateway, a data collector and a
web dashboard. The same system runs in three configurations: plain MQTT (A), MQTT over TLS 1.3 with an ECC (ECDSA
P-256) server certificate (B), and mutual TLS where devices also present ECC certificates (C). Reproducible experiments
measure the cost of each configuration (latency, throughput, connection time, CPU and memory), and a security test suite
shows which attacks each layer stops. In our measurements on localhost, TLS added about 0.30 ms (≈23 %) to median
delivery latency and about 1.5 ms (≈40 %) to connection setup, with 100 % delivery in every mode. Every one of the 10
unauthorised-access attempt types was rejected.

### 2. Objectives
1. Simulate 5–20 IoT devices that publish realistic, structured sensor readings.
2. Secure MQTT with TLS using ECC keys and certificates from a local CA; verify certificates and hostnames.
3. Authenticate clients (password or client certificate) and authorise topics (ACL).
4. Validate messages at a gateway (schema, ranges, replay) and forward only clean data.
5. Store readings, metrics and security events; visualise them in real time.
6. Compare the three configurations with reproducible, measured experiments.

### 3. Architecture
See [architecture.svg](architecture.svg) and [ARCHITECTURE.md](ARCHITECTURE.md).

```
Devices (dev-001…020) ──TLS──▶ Mosquitto broker ──▶ Gateway (validate) ──▶ sensors/<id>/telemetry ──▶ Collector ──▶ SQLite
        │ publish ingest/<own id>     auth + topic ACL        rejects → gateway/events                        │
        └── wire tap (demo eavesdropper) ─────────────────────────────────────────────────────── Next.js web app (live / analytics / benchmarks)
```

| Component | Technology | Role |
|---|---|---|
| Device simulator | Python, paho-mqtt 2.1 | Temperature, humidity, soil moisture; JSON with sequence number and timestamps |
| Broker | Mosquitto 2.1.2 | Listeners: 1884 plain, 8883 TLS, 8884 mTLS; no anonymous access; password file; ACL |
| PKI | OpenSSL 3.2 (Git for Windows), Python `cryptography` | Local CA, broker and 23 client certificates, all ECDSA P-256 / SHA-256 |
| Gateway | Python | Schema + physical-range validation, per-device sequence check (replay, gaps, restarts), reconnect |
| Collector | Python, SQLite (WAL), psutil | Readings + latency, gateway events, broker-log security events, CPU/RAM |
| Web app | Next.js 16, React 19, framer-motion | Live crypto visualizer, analytics, benchmarks, explanations |
| Tests | pytest | Authentication, ACL, TLS/mTLS, hostname, validation, replay, reconnect, secrets |

### 4. Security design
- **Transport:** TLS 1.2 minimum. TLS 1.3 was negotiated in practice, with `TLS_AES_128_GCM_SHA256`, X25519 ECDHE and an
  ECDSA P-256 server certificate. TLS 1.2 is limited to ECDHE-ECDSA-AES-GCM/ChaCha20 suites.
- **Server authentication:** clients use `CERT_REQUIRED`, hostname checking and our CA as the only trust anchor. The SAN
  covers `localhost`, `127.0.0.1` and `::1`. Insecure options are never used, and a test scans the source code for them.
- **Client authentication:** a random per-device password (PBKDF2-SHA512 hash in Mosquitto) in mode B; in mode C a client
  certificate whose CN becomes the MQTT username (`use_identity_as_username`).
- **Authorisation:** each device may only publish to `ingest/<its own id>`; only the gateway may publish validated telemetry.
- **Application layer:** the gateway rejects malformed, out-of-range, oversized, mismatched-ID and replayed messages.
- **Secrets:** private keys and passwords are git-ignored and readable only by the Windows user. Logs pass through a
  redaction filter.

**ECC's role, stated precisely:** ECDSA authenticates the parties and ECDHE agrees the session key. The data itself is
encrypted by the symmetric AES-GCM cipher that TLS negotiates. ECC does not encrypt the MQTT messages directly.

### 5. Experimental methodology
Harness: `backend/app/analytics/benchmark.py`, configuration `backend/config/benchmark.json`.

| Parameter | Value |
|---|---|
| Load | 10 devices × 5 msg/s = 50 msg/s offered, QoS 1 |
| Warm-up / measurement window / drain | 5 s / 30 s / 3 s |
| Repetitions | 3 per configuration, interleaved A,B,C,A,B,C,A,B,C |
| Isolation | Fresh broker and gateway for every run |
| Connection setup | 30 sequential connects per run on the idle system, before the load (connect() → CONNACK) |
| Latency | device → broker → gateway → broker → sink, timed with `perf_counter_ns` (one clock, same host) |
| Success rate | unique (device, seq) received ÷ messages sent inside the window |
| CPU / RAM | psutil, every 1 s during the window; CPU in % of one core |

Why `perf_counter_ns` and not `time.time()`: on Python 3.12/Windows, `time.time()` has 15.6 ms resolution, which is too
coarse for sub-millisecond latencies. QueryPerformanceCounter has 100 ns resolution and is shared by all processes on the host.

### 6. Results (run `20261023-193747`, 4,500 measured messages per configuration)

| Metric | A · Plain | B · TLS (ECC) | C · Mutual TLS |
|---|---|---|---|
| Median latency (pooled) | **1.335 ms** | **1.637 ms** (+22.6 %) | **1.706 ms** (+27.7 %) |
| p95 latency (pooled) | 2.308 ms | 2.472 ms | 3.426 ms |
| p99 latency (pooled) | 3.847 ms | 3.526 ms | 12.027 ms ¹ |
| Throughput (mean) | 50.0 msg/s | 50.0 msg/s | 50.0 msg/s |
| Delivery success | 100 % | 100 % | 100 % |
| Connection setup, median (mean ± std over reps) | 3.73 ± 0.02 ms | 5.20 ± 0.52 ms (+39.4 %) | 5.27 ± 0.58 ms (+41.3 %) |
| Broker CPU (mean, % of one core) | 1.81 % | 2.68 % | 2.56 % |
| Broker memory (max RSS) | 11.1 MB | 14.1 MB | 14.2 MB |
| Client process CPU (fleet + sink) | 6.1 % | 7.2 % | 7.4 % |

¹ One mTLS repetition (r2) had a p95 of 8.06 ms while the other two were ≈2.3–2.5 ms. This looks like a background
pause on the laptop, not a protocol effect. It is kept in the data rather than removed.

**Gateway CPU:** the run above recorded 0 % because the harness measured the Windows venv *launcher* process instead of
the real Python interpreter. This has been fixed (`real_process()` in `analytics/resources.py`). Re-run the benchmark to
get gateway CPU figures; the other metrics are not affected.

**Unauthorised attempts (5 tries each, all must fail):**

| Mode | Attempt | Rejected |
|---|---|---|
| plain, tls | wrong password | 5/5 |
| plain, tls | anonymous | 5/5 |
| tls, mtls | client does not trust the broker (rogue CA trust store) | 5/5 |
| mtls | client certificate from a rogue CA | 5/5 |
| mtls | expired client certificate | 5/5 |
| mtls | wrong-purpose (serverAuth) client certificate | 5/5 |
| mtls | no client certificate | 5/5 |

### 7. Discussion
- **TLS cost is small in absolute terms.** After connection, TLS adds about 0.3 ms per message here: the AES-GCM
  encryption and decryption on two hops (device→broker, broker→gateway, and again to the sink). At 50 msg/s the
  broker's CPU use rose by under 1 percentage point of one core.
- **The handshake is the main cost.** It added about 1.5 ms per connection. For IoT devices that keep long-lived MQTT
  connections, this is paid once; devices that reconnect often pay it repeatedly.
- **mTLS costs barely more than TLS** in steady state (+0.07 ms median), because the client certificate is checked
  only at connection time. In return, a stolen password is useless and identity is bound to a private key.
- **Delivery was lossless** in every configuration at this load, so the security layers did not reduce reliability.
- **Each security layer stops different attacks.** TLS stops eavesdropping and tampering; certificate checks stop
  impostor brokers and unauthorised devices; ACLs stop cross-device writes; the gateway stops valid-but-wrong data and
  replays. The live demo shows each one.

### 8. Visualization and analytics delivered
- **Live demo:** animated, wire-accurate view of the plain vs TLS vs mTLS traffic; 7-stage pipeline; narrated
  handshake with real certificate details; size calculation proving the 16-byte AES-GCM tag (227 B MQTT → 249 B record).
- **Analytics:** throughput, median/p95 latency over time, latency histogram, security events by type and timeline,
  CPU/RAM per process, per-device sensor charts, CSV export.
- **Benchmarks:** comparison bars with error bars, latency CDF, methodology, environment and raw runs.

### 9. Limitations
- Localhost only: results show relative TLS cost, not real-network latency (no Wi-Fi, no packet loss).
- Simulated sensors; no physical hardware (ESP32/Raspberry Pi) or constrained-device CPU measurements.
- Demo CA with keys stored as files, not a hardware security module; no certificate revocation (CRL/OCSP).
- A single broker without high availability; MQTT 3.1.1 cannot report ACL denials to the publisher.
- Three repetitions per configuration: enough to show clear trends, too few for formal significance testing.

### 10. Future scope
- Run devices on an ESP32 (mbedTLS) or Raspberry Pi to measure TLS cost on constrained hardware and over Wi-Fi.
- Add certificate revocation (CRL) and automated certificate rotation; store keys in a TPM/secure element.
- MQTT 5 with enhanced authentication and reason codes for ACL denials.
- Compare P-256 with Ed25519 certificates and post-quantum hybrid key exchange (X25519MLKEM768).
- Anomaly detection on sensor streams and security events (e.g. sudden spikes, repeated failed logins).

### 11. How to reproduce
```powershell
start.bat                                                                    # web app
cd backend
..\.venv\Scripts\python -m pytest -v                                         # tests
powershell -ExecutionPolicy Bypass -File scripts\run_benchmarks.ps1          # experiments → reports\benchmarks\<run>\
```
