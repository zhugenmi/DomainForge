from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager

from app.observability.logging.logger import get_logger

logger = get_logger("metrics")


class _Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timers[name].append(seconds * 1000.0)
            if len(self._timers[name]) > 1024:
                self._timers[name] = self._timers[name][-512:]

    @contextmanager
    def time(self, name: str):
        start = time.time()
        try:
            yield
        finally:
            self.observe(name, time.time() - start)

    def snapshot(self) -> dict:
        with self._lock:
            timers = {}
            for k, vals in self._timers.items():
                if not vals:
                    continue
                timers[k] = {
                    "count": len(vals),
                    "avg_ms": round(sum(vals) / len(vals), 2),
                    "p50_ms": round(sorted(vals)[len(vals) // 2], 2),
                    "max_ms": round(max(vals), 2),
                }
            return {"counters": dict(self._counters), "timers": timers}

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._timers.clear()


metrics = _Metrics()


def log_snapshot() -> None:
    snap = metrics.snapshot()
    logger.info("metrics_snapshot", **snap)


__all__ = ["metrics", "log_snapshot"]
