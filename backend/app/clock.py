"""Timestamps used for latency measurement.

Why not time.time()? On Python 3.12 / Windows it is backed by
GetSystemTimeAsFileTime with a 15.6 ms resolution - far too coarse for
sub-millisecond localhost latencies.

time.perf_counter_ns() uses QueryPerformanceCounter: 100 ns resolution and a
single system-wide counter, so values from different processes ON THE SAME
MACHINE are directly comparable (verified in Phase 3). That is the only
setting this project measures in. Across machines it would be meaningless.
"""
from __future__ import annotations

import time


def mono_ns() -> int:
    """High-resolution, system-wide monotonic timestamp (ns). Use for latency."""
    return time.perf_counter_ns()


def wall() -> float:
    """Unix wall-clock time (s). Use for display/storage, never for latency."""
    return time.time()


def latency_ms(sent_mono_ns: int, received_mono_ns: int) -> float:
    return (received_mono_ns - sent_mono_ns) / 1_000_000
