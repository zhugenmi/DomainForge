import pytest

from app.observability.tracing.tracer import span, request_trace, current_trace_id
from app.observability.metrics.metrics import metrics


def test_tracer_span_nesting():
    with request_trace("outer") as outer:
        outer_tid = outer.trace_id
        with span("inner") as inner:
            assert inner.trace_id == outer_tid
            assert inner.parent_id == outer.span_id
    assert outer.end_ts >= outer.start_ts
    # trace id reset after request_trace exits
    assert current_trace_id() != outer_tid


def test_tracer_records_error():
    with pytest.raises(ValueError):
        with span("fails"):
            raise ValueError("boom")


def test_metrics_counter_and_timer():
    metrics.reset()
    metrics.inc("requests")
    metrics.inc("requests")
    with metrics.time("llm_call"):
        pass
    snap = metrics.snapshot()
    assert snap["counters"]["requests"] == 2
    assert "llm_call" in snap["timers"]
    assert snap["timers"]["llm_call"]["count"] == 1
