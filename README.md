# ECC-Based Secure IoT Gateway with TLS-Enabled MQTT Communication and Real-Time Security Analytics

College project for **IoT Data Analytics and Visualization**. Simulated agricultural IoT devices publish sensor
readings over MQTT to a local Mosquitto broker in three security modes: plain TCP, TLS with ECC (ECDSA P-256)
certificates, and mutual TLS. A secure gateway validates every message, a collector stores readings and security
events in SQLite, and a Next.js web app shows the cryptography live, plus analytics and benchmark results.

> All certificates come from a **local demo CA** generated on this machine. They are not publicly trusted. This is a
> local college demonstration, not a production system. Sensor values are simulated; every other number is measured.

## Start it (Windows)

**Double-click `start.bat`.** It opens two windows (backend API and frontend), then your browser at
**http://localhost:3000**. On the first run it also creates the Python environment, installs the packages, and
generates passwords and certificates.

Manual start (two terminals, from the project folder):

```powershell
# terminal 1: backend API (http://127.0.0.1:8600)
powershell -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1

# terminal 2: frontend (http://localhost:3000)
cd frontend
npm install        # first time only
npm run dev
```

Requirements: Python 3.12, Node.js 20+, Git for Windows (provides OpenSSL 3), Eclipse Mosquitto 2.x in
`C:\Program Files\mosquitto`. See [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md).

## What's in the web app

| Page | What it shows |
|---|---|
| **Live demo** `/` | Choose Plain / TLS / mutual TLS and press Start. An animated message path shows the sensors → device → eavesdropper → broker → gateway. Each moving packet is a real TLS record or MQTT packet captured on the wire. Also: a 7-stage "where is the message now" tracker, a narrator that explains each step with an analogy, the journey of a reading (plaintext → ciphertext → validated), the TLS handshake step by step with real certificate details, 12 trigger buttons (readings + 10 attacks) with observed verdicts, and live logs. |
| **Analytics** `/analytics` | Data the collector stored in SQLite: throughput, median/p95 latency, latency histogram, security events by type, CPU/RAM per process, per-device sensor charts, CSV export. Start an 8-device fleet from the page. |
| **Benchmarks** `/benchmarks` | Experiments A (plain), B (TLS), C (mTLS): key findings computed from the data, median/p95 latency, connection setup time, throughput, CPU, latency CDF, the methodology, and the unauthorised-attempt results. |
| **Learn** `/learn` | Animated explainers: ECDHE as paint mixing, the TLS 1.3 handshake message by message, the anatomy of an encrypted record, concept cards and an attack-to-defence map. |

## Project structure

```
start.bat                one-click start (backend + frontend)
backend/                 all Python code and runtime data
  app/
    visualizer/          API server (server.py), live session, wire tap (eavesdropper), scenarios
    gateway/             validation (schema, ranges, replay) + forwarding
    simulator/           sensor model, single device, 1-20 device fleet
    analytics/           collector, SQLite, broker-log parser, resources, benchmark harness, API queries
    mqtt/                client_factory.py: the only place MQTT/TLS clients are built
    dashboard/           optional Streamlit dashboard (alternative UI)
  config/                Mosquitto configs (plain/tls/mtls), ACL, openssl.cnf, benchmark.json
  scripts/               start_backend, gen_certs, setup_credentials, run_benchmarks, check_env
  tests/                 pytest: auth, ACL, TLS/mTLS, gateway, replay, reconnect, secrets
  certificates/ data/ logs/   generated at runtime (git-ignored)
  reports/benchmarks/    raw + aggregated benchmark CSVs
frontend/                Next.js 16 app (React 19, framer-motion)
  app/                   pages: / (live), /analytics, /benchmarks, /learn
  components/            live/, learn/, charts, nav, overlays
  lib/                   api.ts, live.tsx (shared SSE connection), visualizer.ts (event → visual state)
docs/                    architecture, setup, report, viva guide, test evidence, demo script
```

## Ports (all bound to loopback only)

| Port | Use |
|---|---|
| 1884 / 8883 / 8884 | Mosquitto: plain / TLS / mutual TLS (1884, not 1883, so it never clashes with the Windows Mosquitto service) |
| 11884 / 18883 / 18884 | Wire tap (the eavesdropper relay) in front of each broker mode |
| 8600 | Backend API (`backend/app/visualizer/server.py`) |
| 3000 | Next.js frontend |

## Other commands (run inside `backend\`)

```powershell
..\.venv\Scripts\python -m pytest -v                                         # automated tests
powershell -ExecutionPolicy Bypass -File scripts\run_benchmarks.ps1          # Experiments A/B/C (~8 min)
..\.venv\Scripts\python -m app.run_demo --mode mtls --devices 10             # headless system + Streamlit dashboard
```
Stop the live session (Stop button) before running benchmarks or `run_demo`; they use the same broker ports.

## Documentation
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): design, data flow, metric definitions, verified behaviour
- [docs/architecture.svg](docs/architecture.svg): architecture diagram
- [docs/REPORT.md](docs/REPORT.md): project report (methodology, results, limitations, future scope)
- [docs/VIVA_GUIDE.md](docs/VIVA_GUIDE.md): viva preparation
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md): how to demonstrate the project
- [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md): security tests, expected vs actual, evidence
- [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md): installation and troubleshooting
