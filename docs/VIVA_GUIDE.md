# Viva preparation guide

Short, accurate answers. Each one points to where you can **show** it in the project.

## The project in 30 seconds
"I built a simulated IoT system where sensors send data over MQTT through a broker to a gateway. I secured it with
TLS 1.3 using ECC certificates from my own CA, then mutual TLS. The gateway validates every message, and everything is
stored in SQLite and visualised in a web app. I measured the cost of each security level with reproducible
experiments, and I tested 10 kinds of attacks. All of them were blocked."

## Core concepts

**What is MQTT?** A lightweight publish/subscribe protocol. Clients publish to topics; the broker forwards messages
to subscribers. It's popular for IoT because the headers are tiny (2 bytes minimum). On its own it has no encryption.

**Encryption vs authentication vs integrity?**
Encryption = nobody else can read it (AES-GCM). Authentication = proof of who you are (certificates, passwords).
Integrity = proof nothing was changed (the GCM tag). TLS gives all three. *Show:* Learn page, concept cards.

**What is ECC and why use it?** Public-key cryptography on elliptic curves. A 256-bit P-256 key gives about the same
security as a 3072-bit RSA key (NIST SP 800-57), so certificates and handshakes are smaller and faster: good for IoT.

**ECDSA vs ECDHE?** ECDSA = signatures (who you are). The CA signs certificates, and each side signs the handshake
(CertificateVerify). ECDHE = key agreement (a shared secret without sending it). "E" = ephemeral: new keys per
connection, giving forward secrecy. *Show:* Learn → paint-mixing animation.

**Does ECC encrypt the MQTT messages?** No. ECDHE agrees the key; AES-128-GCM (symmetric) encrypts the data.

**Which curve did the key exchange actually use?** X25519, chosen by TLS 1.3. It is also an elliptic curve
(Curve25519). P-256 is used for the certificates/signatures. We observed this in the ServerHello rather than assuming it.
*Show:* Live demo → handshake step "ServerHello".

**What is forward secrecy?** Each session key comes from throw-away ECDHE keys. Recorded traffic stays unreadable
even if the broker's long-term private key leaks later.

**What is mutual TLS?** Both sides present certificates. The broker accepts only devices with a certificate from our
CA, and the certificate CN (dev-001) becomes the MQTT username used by the ACL.

**What does the CA do?** It signs certificates. Clients trust only our CA certificate, so only certificates it signed
are accepted. Ours is a local demo CA, not publicly trusted.

**What is a SAN, and why check the hostname?** Subject Alternative Name: the names a certificate is valid for
(`localhost`, `127.0.0.1`, `::1`). Without a hostname check, any valid certificate from the CA could impersonate the
broker. We test a CA-signed certificate for `wrong.example`, and it is rejected.

**What is in a TLS record?** A 5-byte header, the encrypted data, 1 hidden content-type byte and a 16-byte GCM tag.
We measured a 227-byte MQTT packet becoming a 249-byte record. *Show:* Live demo → journey card ②.

## Design decisions
| Decision | Why |
|---|---|
| Gateway is an MQTT client behind the broker | The standard edge pattern; the ACL prevents devices from bypassing it |
| Devices may only write `ingest/<own id>` | Least privilege: a compromised device can't fake others' data |
| Ports 1884/8883/8884 | Avoid clashing with the Windows Mosquitto service on 1883 |
| `listener … localhost` | Binds both IPv4 and IPv6 loopback; binding only 127.0.0.1 made connections take ~2 s |
| `perf_counter_ns` for latency | `time.time()` has 15.6 ms resolution on Python 3.12/Windows |
| One broker mode at a time, fresh per run | Clean, comparable measurements |
| Sequence numbers + timestamps | Detect loss, duplicates and replays at the gateway |
| SQLite in WAL mode | Collector writes while the dashboard reads; no server needed |
| No Docker | Too heavy for 8 GB RAM; native is simpler to explain |

## Likely questions

**How did you measure latency?** The device stamps `perf_counter_ns()` into the message; the receiver subtracts it on
arrival. This is valid only because everything runs on one machine with one shared clock.

**Why is connection time separate from latency?** The handshake happens once per connection; latency is per message.
Mixing them would hide both effects.

**What were your results?** Median latency 1.34 ms plain, 1.64 ms TLS, 1.71 ms mTLS; connection setup 3.7 ms vs
5.2–5.3 ms; 100 % delivery everywhere; all 10 attack types rejected. TLS's main cost is the one-time handshake.

**Why only localhost?** No hardware budget. Localhost isolates the CPU cost of cryptography; real networks add
milliseconds of network delay, which would dominate.

**How do you prevent replay attacks?** In TLS mode an outsider can't inject anything at all. At the application level,
the gateway tracks each device's last sequence number and timestamp and rejects anything old. *Show:* Replay scenario.

**What happens if the broker crashes?** paho reconnects automatically and the gateway re-subscribes. A test kills and
restarts the broker and checks that traffic flows again.

**How are secrets protected?** Random per-device passwords (hashed by Mosquitto), private keys readable only by the
Windows user, all git-ignored (a test checks `git ls-files`), and log redaction.

**Is it production-ready?** No. It's a local demonstration: a demo CA, keys on disk, no revocation, a single broker.
See REPORT.md §9.

**What would you add next?** Real ESP32 devices, certificate revocation, MQTT 5, anomaly detection.

## A bug I found and fixed (good to mention)
The benchmark first reported 0 % gateway CPU. On Windows a venv's `python.exe` is a launcher that starts the real
interpreter as a child process, so I had been measuring the launcher. I fixed it by following the child process. It
shows why you should question measurements that look too good.
