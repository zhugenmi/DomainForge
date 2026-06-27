from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Any

from app.observability.logging.logger import get_logger

logger = get_logger("metrics")

# ---- OTel API 镜像（可选） ----
_otel_meter = None
try:
    from opentelemetry import metrics as otel_metrics

    try:
        _otel_meter = otel_metrics.get_meter("domainforge")
    except Exception:  # pragma: no cover - 无 TracerProvider 时 get_meter 也安全
        _otel_meter = None
except ImportError:  # pragma: no cover
    pass


class _Metrics:
    """进程内 metrics，同时镜像到 OTel API。

    snapshot() 保留旧结构 {counters, timers: {name: {count, avg_ms, p50_ms, max_ms}}}，
    供 /admin/metrics 消费；OTel 侧由 reader/exporter 聚合导出。
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._otel_counters: dict[str, Any] = {}
        self._otel_histograms: dict[str, Any] = {}

    def _otel_counter(self, name: str):
        if _otel_meter is None:
            return None
        if name not in self._otel_counters:
            self._otel_counters[name] = _otel_meter.create_counter(
                name, description=f"counter: {name}"
            )
        return self._otel_counters[name]

    def _otel_histogram(self, name: str):
        if _otel_meter is None:
            return None
        if name not in self._otel_histograms:
            self._otel_histograms[name] = _otel_meter.create_histogram(
                name, unit="ms", description=f"histogram: {name}"
            )
        return self._otel_histograms[name]

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value
        c = self._otel_counter(name)
        if c is not None:
            c.add(value)

    def observe(self, name: str, seconds: float) -> None:
        ms = seconds * 1000.0
        with self._lock:
            self._timers[name].append(ms)
            if len(self._timers[name]) > 1024:
                self._timers[name] = self._timers[name][-512:]
        h = self._otel_histogram(name)
        if h is not None:
            h.record(ms)

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
