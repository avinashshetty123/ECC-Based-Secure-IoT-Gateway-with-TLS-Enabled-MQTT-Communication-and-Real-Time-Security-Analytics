"""Thread-safe fan-out of live events to every connected browser (Server-Sent Events)."""
from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque


class EventBus:
    def __init__(self, history: int = 400):
        self._subscribers: set[queue.Queue] = set()
        self._history: deque[dict] = deque(maxlen=history)
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def publish(self, kind: str, **data) -> dict:
        event = {"id": next(self._ids), "ts": time.time(), "kind": kind, **data}
        with self._lock:
            self._history.append(event)
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except queue.Full:  # a stalled browser tab must not block the system
                    pass
        return event

    def subscribe(self, replay: bool = True) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2000)
        with self._lock:
            if replay:
                for e in self._history:
                    q.put_nowait({**e, "replay": True})
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)
