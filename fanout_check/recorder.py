"""Opt-in single-process recorder. Never captures arguments or return values."""
import asyncio
from contextlib import contextmanager
import threading
import time

from .core import _label


class Recorder:
    """Measure the exact block inside each span, including awaits and queue waits.

    Put spans INSIDE a semaphore if you want to measure running work rather than
    time waiting for admission. Do not nest spans in the same logical group.
    """

    def __init__(self):
        self._origin = time.perf_counter_ns()
        self._lock = threading.Lock()
        self._spans = []

    @contextmanager
    def span(self, name, *, group):
        _label(name, "/name")
        _label(group, "/group")
        with self._lock:
            entry = {"id": str(len(self._spans) + 1), "name": name, "group": group,
                     "start_ns": time.perf_counter_ns() - self._origin,
                     "end_ns": None, "status": "running"}
            self._spans.append(entry)
        status = "ok"
        try:
            yield
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except BaseException:
            status = "error"
            raise
        finally:
            with self._lock:
                entry["end_ns"] = time.perf_counter_ns() - self._origin
                entry["status"] = status

    def trace(self):
        """Copy the current trace; active spans remain explicitly unfinished."""
        with self._lock:
            return {"version": 1, "clock": "monotonic", "spans": [dict(s) for s in self._spans]}
