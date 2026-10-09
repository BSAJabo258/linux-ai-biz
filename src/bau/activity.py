"""What Jarvis is doing right now, for the screen: a small in-memory feed of events.

Each event names the node on the Jarvis screen it belongs to (producer, scout, ...), so
the page can light that node up while work is running and show its progress. Nothing here
is a record: the audit chain is the record; this is only what is on screen.
"""

from __future__ import annotations

import datetime as dt
import threading
from collections import deque
from typing import Any

KINDS = ("start", "progress", "done", "error")


class Activity:
    def __init__(self, size: int = 200):
        self._events: deque[dict[str, Any]] = deque(maxlen=size)
        self._busy: dict[str, str] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def emit(self, node: str, kind: str, text: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"unknown activity kind {kind!r}")
        with self._lock:
            self._seq += 1
            self._events.append({"seq": self._seq, "node": node, "kind": kind,
                                 "text": str(text)[:300],
                                 "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")})
            if kind in ("start", "progress"):
                self._busy[node] = str(text)[:300]
            else:
                self._busy.pop(node, None)

    def since(self, seq: int) -> dict[str, Any]:
        with self._lock:
            return {"seq": self._seq, "events": [e for e in self._events if e["seq"] > seq],
                    "busy": dict(self._busy)}
