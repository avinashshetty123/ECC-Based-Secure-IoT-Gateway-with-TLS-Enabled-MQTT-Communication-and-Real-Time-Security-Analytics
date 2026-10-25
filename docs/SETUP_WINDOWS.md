# Setup guide: Windows 11

Everything is free and runs offline after installation. Developed on Windows 11 Home (build 26200),
Intel Core i3-1115G4, 8 GB RAM.

## 1. Install the tools (once)

| Tool | Where | Notes |
|---|---|---|
| Python 3.12 (64-bit) | https://www.python.org/downloads/windows/ | Tick **"Add python.exe to PATH"** |
| Node.js 20 LTS or newer | https://nodejs.org/ | For the Next.js frontend |
| Git for Windows | https://git-scm.com/download/win | Also provides OpenSSL 3 at `C:\Program Files\Git\usr\bin\openssl.exe` |
| Eclipse Mosquitto 2.x (64-bit) | https://mosquitto.org/download/ | Default folder `C:\Program Files\mosquitto` |

The Mosquitto installer also creates a Windows service on port 1883. **You can leave it running.** This project
uses ports 1884, 8883 and 8884.

## 2. Start

**Easiest: double-click `start.bat`** in the project folder. On the first run it:
1. creates `.venv` and installs `backend\requirements.txt`,
2. runs `npm install` in `frontend\`,
3. generates per-device passwords and the demo ECC certificates (from the backend window),
4. opens http://localhost:3000.

**Manual** (PowerShell, project folder):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements.txt
powershell -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1      # window 1
cd frontend; npm install; npm run dev                                         # window 2
```

Check the tools at any time: `powershell -ExecutionPolicy Bypass -File backend\scripts\check_env.ps1`

## 3. Other tasks (PowerShell inside `backend\`)

| Task | Command |
|---|---|
| Automated tests | `..\.venv\Scripts\python -m pytest -v` |
| Benchmarks A/B/C (~8 min) | `powershell -ExecutionPolicy Bypass -File scripts\run_benchmarks.ps1` |
| Quick benchmark (~1.5 min) | `powershell -ExecutionPolicy Bypass -File scripts\run_benchmarks.ps1 --quick` |
| Regenerate certificates | `powershell -ExecutionPolicy Bypass -File scripts\gen_certs.ps1 -Force` |
| Regenerate passwords | `..\.venv\Scripts\python scripts\setup_credentials.py --force` |
| Headless system + Streamlit | `..\.venv\Scripts\python -m app.run_demo --mode mtls --devices 10` → http://127.0.0.1:8501 |

Benchmarks, tests and `run_demo` start their own brokers, so press **Stop** in the web app first.

## 4. Troubleshooting

| Symptom | Fix |
|---|---|
| Web app shows "The backend is not running" | Start `backend\scripts\start_backend.ps1` (or `start.bat`) and keep its window open |
| `Port 8884 is already in use` | Another broker is running (a benchmark/test/run_demo). Close it, or press Stop in the web app |
| `port 8600 is already in use` | The backend is already running in another window |
| `npm` not recognised | Install Node.js and reopen the terminal |
| `running scripts is disabled on this system` | Use `powershell -ExecutionPolicy Bypass -File ...` or the `.bat` file |
| A valid device gets `Not authorized` | Passwords were regenerated while a broker was running: press Stop, then Start |
| A valid device gets `certificate verification failed` | Certificates were regenerated while a broker was running: press Stop, then Start |
| `mosquitto.exe not found` | Set `MOSQUITTO_DIR` in `backend\.env` (copy from `.env.example`) |
| `openssl ... failed` | Set `OPENSSL_BIN` in `backend\.env` |
| Analytics page is empty | Start the system on the Live demo and turn on the fleet, or pick "All data" |
| Benchmark numbers vary a lot | Plug in the charger, close browsers/heavy apps, re-run |

## 5. Security notes
- Private keys, `backend\config\secrets\` and `backend\data\` are git-ignored. A test checks that Git never tracks them.
- `gen_certs.ps1` limits every private key file to your Windows account (`icacls`).
- Broker, backend API and frontend all bind to loopback only; CORS allows only loopback origins.
- The project folder is inside OneDrive, so OneDrive uploads the generated demo private keys. They are demo keys
  only, but you can move the folder to e.g. `C:\dev\iot-secure-gateway` (recreate `.venv` after moving).
