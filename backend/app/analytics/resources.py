"""CPU / memory sampling of the project's own processes (psutil)."""
from __future__ import annotations

import threading
import time
from typing import Callable

import psutil

# process label -> substring that identifies it on the command line
PATTERNS = {
    "broker": "broker_",                 # mosquitto -c config/.../broker_<mode>.conf (not the Windows service)
    "gateway": "app.gateway",
    "collector": "app.analytics.collector",
    "fleet": "app.simulator.fleet",
    "backend": "app.visualizer",          # API server (runs gateway + collector + fleet in-process)
}


def real_process(p: psutil.Process) -> psutil.Process:
    """On Windows a venv's python.exe is a launcher that starts the REAL interpreter as a child
    with the same command line. Measuring the launcher would report ~0 % CPU, so follow it."""
    try:
        for child in p.children():
            if "python" in child.name().lower():
                return child
    except psutil.Error:
        pass
    return p


def find_processes() -> dict[str, psutil.Process]:
    found: dict[str, psutil.Process] = {}
    for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        for label, pat in PATTERNS.items():
            if pat not in cmd:
                continue
            if label == "broker" and "mosquitto" not in (p.info["name"] or "").lower():
                continue
            # launcher and real interpreter share the command line: keep the bigger one (the real one)
            mem = p.info["memory_info"].rss if p.info["memory_info"] else 0
            prev = found.get(label)
            if prev is None or mem > (prev.info["memory_info"].rss if prev.info.get("memory_info") else 0):
                found[label] = p
    return found


class ResourceSampler(threading.Thread):
    """Every `interval` s, emit {ts, process, pid, cpu_pct, rss_mb} rows via `sink`.

    cpu_pct is psutil's per-process percentage: 100 = one full core.
    `processes` may be given explicitly (benchmarks); otherwise they are discovered.
    """

    def __init__(self, sink: Callable[[list[dict]], None], interval: float = 2.0,
                 processes: dict[str, psutil.Process] | None = None, run_id: str | None = None):
        super().__init__(daemon=True)
        self.sink, self.interval, self.run_id = sink, interval, run_id
        self.fixed = processes
        self.procs: dict[str, psutil.Process] = {}
        self._stop = threading.Event()

    def _refresh(self) -> None:
        current = self.fixed if self.fixed is not None else find_processes()
        for label, p in current.items():
            if label not in self.procs or self.procs[label].pid != p.pid:
                try:
                    p.cpu_percent(None)  # prime the counter
                except psutil.Error:
                    continue
                self.procs[label] = p

    def run(self) -> None:
        self._refresh()
        last_refresh = time.time()
        while not self._stop.wait(self.interval):
            if self.fixed is None and time.time() - last_refresh > 10:
                self._refresh()
                last_refresh = time.time()
            rows = []
            for label, p in list(self.procs.items()):
                try:
                    rows.append({"ts": time.time(), "process": label, "pid": p.pid, "cpu_pct": p.cpu_percent(None),
                                 "rss_mb": p.memory_info().rss / 1_048_576, "run_id": self.run_id})
                except psutil.Error:
                    self.procs.pop(label, None)
            if rows:
                self.sink(rows)

    def stop(self) -> None:
        self._stop.set()
