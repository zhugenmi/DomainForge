from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.observability.logging.logger import get_logger

logger = get_logger("tracing")

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_span_stack_var: contextvars.ContextVar[list["Span"]] = contextvars.ContextVar(
    "span_stack", default=[]
)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    tid = _trace_id_var.get()
    return tid or new_trace_id()


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_id: str = ""
    start_ts: float = 0.0
    end_ts: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        if not self.end_ts:
            return 0.0
        return (self.end_ts - self.start_ts) * 1000.0


@contextmanager
def span(name: str, **attributes):
    """同步 span。嵌套时自动设置 parent_id。"""
    tid = _trace_id_var.get() or new_trace_id()
    _trace_id_var.set(tid)
    stack = _span_stack_var.get()
    parent_id = stack[-1].span_id if stack else ""
    s = Span(name=name, trace_id=tid, parent_id=parent_id, start_ts=time.time(), attributes=dict(attributes))
    stack = [*stack, s]
    token = _span_stack_var.set(stack)
    try:
        yield s
    except Exception as e:
        s.error = repr(e)
        logger.error("span_error", span=name, trace_id=tid, error=str(e))
        raise
    finally:
        s.end_ts = time.time()
        logger.info(
            "span_end",
            span=s.name,
            trace_id=s.trace_id,
            span_id=s.span_id,
            parent_id=s.parent_id,
            duration_ms=round(s.duration_ms, 2),
            error=s.error,
            attrs=s.attributes,
        )
        _span_stack_var.reset(token)


@contextmanager
def request_trace(name: str = "request", **attributes):
    """开启一个新 trace（重置 trace_id）。"""
    tid = new_trace_id()
    token = _trace_id_var.set(tid)
    try:
        with span(name, **attributes) as s:
            yield s
    finally:
        _trace_id_var.reset(token)


__all__ = ["span", "request_trace", "current_trace_id", "new_trace_id", "Span"]
