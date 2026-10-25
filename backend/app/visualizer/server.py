"""Backend API for the Next.js frontend (Python standard library HTTP server).

  cd backend
  ..\\.venv\\Scripts\\python -m app.visualizer          -> API on http://127.0.0.1:8600

Binds to 127.0.0.1 only; CORS allows loopback origins (the Next.js dev server on :3000).

Live system
  GET  /events                 Server-Sent Events stream of live events
  GET  /api/state              session + scenario catalogue
  POST /api/start              {"mode": "plain"|"tls"|"mtls"}
  POST /api/stop
  POST /api/trigger            {"name": "<scenario>"}
  POST /api/stream             {"enabled": true, "interval": 2}           dev-001 auto readings
  POST /api/fleet              {"enabled": true, "devices": 8, "rate": 1, "invalid_every": 30}
Analytics (read from SQLite / benchmark CSVs)
  GET  /api/analytics/overview?window=300
  GET  /api/analytics/sensors?window=300&devices=dev-001,dev-002
  GET  /api/export/<table>.csv?window=300   readings | security_events | connection_events | resource_samples
  GET  /api/benchmarks         list of benchmark runs
  GET  /api/benchmarks/<run>   one run (use "latest" for the newest)
"""
from __future__ import annotations

import argparse
import json
import queue
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app.analytics import api as analytics
from app.config import MODES
from app.visualizer import scenarios
from app.visualizer.events import EventBus
from app.visualizer.session import DemoSession

LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
BUS = EventBus()
SESSION = DemoSession(BUS)


class Handler(BaseHTTPRequestHandler):
    server_version = "IoTGatewayAPI/2.0"

    def log_message(self, fmt, *args):  # keep the console quiet; events go to the UI
        pass

    # ------------------------------------------------------------------ helpers
    def end_headers(self):
        origin = self.headers.get("Origin", "")
        if LOCAL_ORIGIN.match(origin):  # loopback only, never the internet
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json(self, obj, status=HTTPStatus.OK):
        body = json.dumps(obj, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    @staticmethod
    def _background(fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    # ------------------------------------------------------------------ routes
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        window = float(q["window"]) if q.get("window") not in (None, "", "all") else None
        try:
            if url.path == "/":
                self._json({"service": "IoT gateway backend API", "frontend": "http://localhost:3000",
                            "docs": "see backend/app/visualizer/server.py"})
            elif url.path == "/api/state":
                self._json({"session": SESSION.state(), "scenarios": scenarios.catalog()})
            elif url.path == "/events":
                self._sse()
            elif url.path == "/api/analytics/overview":
                self._json(analytics.overview(window))
            elif url.path == "/api/analytics/sensors":
                devices = [d for d in q.get("devices", "").split(",") if d]
                self._json(analytics.sensors(window, devices))
            elif url.path.startswith("/api/export/"):
                csv = analytics.export_csv(url.path.rsplit("/", 1)[1].removesuffix(".csv"), window)
                if csv is None:
                    return self._json({"error": "unknown table"}, HTTPStatus.NOT_FOUND)
                body = csv.encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{url.path.rsplit("/", 1)[1].removesuffix(".csv")}.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/benchmarks":
                self._json(analytics.benchmark_runs())
            elif url.path.startswith("/api/benchmarks/"):
                result = analytics.benchmark(url.path.rsplit("/", 1)[1])
                self._json(result or {"error": "no benchmark results"}, HTTPStatus.OK if result else HTTPStatus.NOT_FOUND)
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:  # noqa: BLE001 - report instead of dropping the connection
            self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        data = self._body()
        if self.path == "/api/start":
            mode = data.get("mode")
            if mode not in MODES:
                return self._json({"error": f"mode must be one of {MODES}"}, HTTPStatus.BAD_REQUEST)
            if SESSION.starting:
                return self._json({"error": "already starting - please wait"}, HTTPStatus.CONFLICT)
            SESSION.starting = True  # set before the thread runs, so a quick second click is refused
            self._background(SESSION.start, mode)
        elif self.path == "/api/stop":
            self._background(SESSION.stop)
        elif self.path == "/api/trigger":
            self._background(scenarios.run, SESSION, str(data.get("name", "")))
        elif self.path == "/api/stream":
            SESSION.set_streaming(bool(data.get("enabled")), float(data.get("interval", 2)))
        elif self.path == "/api/fleet":
            self._background(SESSION.set_fleet, bool(data.get("enabled")), int(data.get("devices", 8)),
                             float(data.get("rate", 1)), int(data.get("invalid_every", 30)))
        else:
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        self._json({"accepted": True}, HTTPStatus.ACCEPTED)

    def _sse(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = BUS.subscribe(replay=False)
        try:
            self.wfile.write(f"data: {json.dumps({'kind': 'hello', 'session': SESSION.state()})}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(event, default=str)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            BUS.unsubscribe(q)


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # A browser tab closing mid-request is normal; don't print a traceback for it.
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def main() -> int:
    p = argparse.ArgumentParser(description="IoT gateway backend API")
    p.add_argument("--port", type=int, default=8600)
    args = p.parse_args()

    try:
        server = QuietServer(("127.0.0.1", args.port), Handler)
    except OSError:
        print(f"ERROR: port {args.port} is already in use - the backend is probably already running.", flush=True)
        return 1
    print(f"\n  Backend API running at http://127.0.0.1:{args.port}"
          f"\n  Start the frontend:  cd frontend && npm run dev   ->  http://localhost:3000"
          f"\n  Press Ctrl+C here to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        SESSION.stop(quiet=True)
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
