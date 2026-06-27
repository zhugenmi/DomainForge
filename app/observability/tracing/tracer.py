from __future__ import annotations

import contextvars
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.configs.settings import settings
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
    """对外 Span 视图。内部 span 已迁移到 OTel；本 dataclass 为兼容层，
    让现有调用方（auth.py 的 span.trace_id、测试断言）零改动。"""
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


# ---- OTel SDK 初始化 ----

_tracer = None
_otel_available = False

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    _otel_available = True
except ImportError:  # pragma: no cover
    logger.warning("opentelemetry-sdk 不可用，tracing 退化到自研实现")


def _init_tracer() -> None:
    global _tracer
    if _tracer is not None or not _otel_available:
        return

    resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
    sampler = ParentBased(TraceIdRatioBased(settings.OTEL_TRACES_SAMPLER_RATIO))
    provider = TracerProvider(resource=resource, sampler=sampler)

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
            )
        except ImportError:
            logger.warning("opentelemetry-exporter-otlp 未安装，回退 console")
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    otel_trace.set_tracer_provider(provider)
    _tracer = otel_trace.get_tracer("domainforge")


_init_tracer()


def _otel_span_id(otel_span) -> str:
    ctx = otel_span.get_span_context()
    return format(ctx.span_id, "016x") if ctx and ctx.span_id else ""


def _otel_trace_id(otel_span) -> str:
    ctx = otel_span.get_span_context()
    return format(ctx.trace_id, "032x") if ctx and ctx.trace_id else ""


@contextmanager
def span(name: str, **attributes):
    """同步 span。嵌套时 parent_id 由本模块 span 栈管理（与 OTel context 同步）。"""
    tid = _trace_id_var.get() or new_trace_id()
    tid_token = _trace_id_var.set(tid)

    stack = _span_stack_var.get()
    parent_id = stack[-1].span_id if stack else ""

    s = Span(
        name=name,
        trace_id=tid,
        parent_id=parent_id,
        start_ts=time.time(),
        attributes=dict(attributes),
    )
    stack_token = _span_stack_var.set([*stack, s])

    try:
        if _otel_available and _tracer is not None:
            with _tracer.start_as_current_span(name, attributes=attributes) as otel_span:
                s.span_id = _otel_span_id(otel_span) or s.span_id
                otel_trace_id = _otel_trace_id(otel_span)
                if otel_trace_id:
                    s.trace_id = otel_trace_id
                try:
                    yield s
                except Exception as e:
                    s.error = repr(e)
                    otel_span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR, str(e)))
                    otel_span.record_exception(e)
                    logger.error("span_error", span=name, trace_id=tid, error=str(e))
                    raise
                finally:
                    s.end_ts = time.time()
                    _log_span_end(s)
        else:
            try:
                yield s
            except Exception as e:
                s.error = repr(e)
                logger.error("span_error", span=name, trace_id=tid, error=str(e))
                raise
            finally:
                s.end_ts = time.time()
                _log_span_end(s)
    finally:
        _span_stack_var.reset(stack_token)
        _trace_id_var.reset(tid_token)


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


def _log_span_end(s: Span) -> None:
    """保留旧 span_end 日志格式，供日志聚合系统消费。"""
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


__all__ = ["span", "request_trace", "current_trace_id", "new_trace_id", "Span"]
