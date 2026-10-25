# Backend: Python

Everything that talks MQTT, does cryptography or stores data. Uses the virtual environment at the project root
(`..\.venv`). Run commands from this `backend\` folder.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_backend.ps1    # API on http://127.0.0.1:8600
```
On first start it generates per-device passwords (`config\secrets\`) and the demo ECC certificates (`certificates\`).

## API (consumed by ../frontend)
| Method | Path | Purpose |
|---|---|---|
| GET | `/events` | Server-Sent Events: wire records, connections, gateway decisions, broker log, verdicts |
| GET | `/api/state` | session + scenario catalogue |
| POST | `/api/start` `{"mode":"plain"\|"tls"\|"mtls"}` | start broker + wire tap + gateway + collector + dev-001 |
| POST | `/api/stop` | stop everything |
| POST | `/api/trigger` `{"name": ...}` | run a scenario (reading, reconnect, 10 attacks) |
| POST | `/api/stream` `{"enabled": true}` | dev-001 sends a reading every 2 s |
| POST | `/api/fleet` `{"enabled": true, "devices": 8}` | extra devices dev-002… for the analytics |
| GET | `/api/analytics/overview?window=300` | KPIs, latency/throughput series, histogram, security, resources |
| GET | `/api/analytics/sensors?window=300&devices=dev-002` | per-device sensor series |
| GET | `/api/export/<table>.csv?window=300` | CSV export |
| GET | `/api/benchmarks`, `/api/benchmarks/latest` | benchmark runs and results |

## Components
- `app/visualizer/`: API server, live session, **wire tap** (eavesdropper relay that parses TLS/MQTT), scenarios
- `app/gateway/`: schema/range validation, replay/gap detection, forwarding, reconnect
- `app/simulator/`: sensor model, device, fleet (1–20 devices)
- `app/analytics/`: collector → SQLite, Mosquitto log parser, psutil sampling, benchmark harness, API queries
- `app/mqtt/client_factory.py`: strict TLS contexts (CERT_REQUIRED, hostname check, TLS ≥ 1.2)
- `config/`: `broker_plain|tls|mtls.conf`, `acl.conf`, `openssl.cnf`, `benchmark.json`

## Other commands
```powershell
..\.venv\Scripts\python -m pytest -v                                  # tests (each starts its own broker)
powershell -ExecutionPolicy Bypass -File scripts\run_benchmarks.ps1   # Experiments A/B/C (~8 min)
powershell -ExecutionPolicy Bypass -File scripts\gen_certs.ps1 -Force # regenerate the demo PKI
..\.venv\Scripts\python -m app.run_demo --mode mtls                   # headless system + Streamlit dashboard
```
