"""模块 02 OTel 迁移新增测试。

覆盖计划 §4 验证矩阵：
- test_tracer_otel_span：request_trace 开启后 OTel span 有 trace_id/attributes
- test_tracer_otel_parent_child：嵌套 span 的 parent_id 正确
- test_tracer_console_exporter_no_otlp：未配 OTLP endpoint 时不报错
- test_metrics_otel_counter：inc 后 snapshot 反映计数
- test_metrics_otel_histogram：observe 后 snapshot 反映 p50/max
- test_eval_llm_judge_with_mock_llm：mock LLM 返回评分，正确落 eval_results
"""
import pytest

from app.observability.tracing.tracer import (
    Span,
    span,
    request_trace,
    current_trace_id,
)
from app.observability.metrics.metrics import metrics
from app.evals.metrics import llm_judge


def test_tracer_otel_span():
    """request_trace 开启后 Span 有 trace_id 与 attributes。"""
    with request_trace("outer", user="alice") as s:
        assert isinstance(s, Span)
        assert s.trace_id  # 非空
        assert s.attributes == {"user": "alice"}
        assert s.start_ts > 0
    assert s.end_ts >= s.start_ts
    assert s.duration_ms >= 0


def test_tracer_otel_parent_child():
    """嵌套 span 的 parent_id 指向父 span。"""
    with request_trace("outer") as outer:
        outer_tid = outer.trace_id
        assert outer.parent_id == ""  # 顶层无父
        with span("inner") as inner:
            assert inner.trace_id == outer_tid
            assert inner.parent_id == outer.span_id
    # request_trace 退出后 trace_id 重置
    assert current_trace_id() != outer_tid


def test_tracer_console_exporter_no_otlp():
    """未配 OTLP endpoint 时 console exporter 不报错。"""
    from app.configs.settings import settings

    assert settings.OTEL_EXPORTER_OTLP_ENDPOINT == ""  # 默认未配
    with request_trace("no_otlp_test") as s:
        s.attributes["ok"] = True
    # 不抛异常即通过


def test_metrics_otel_counter():
    metrics.reset()
    metrics.inc("requests")
    metrics.inc("requests")
    metrics.inc("errors", 2)
    snap = metrics.snapshot()
    assert snap["counters"]["requests"] == 2
    assert snap["counters"]["errors"] == 2


def test_metrics_otel_histogram():
    metrics.reset()
    for s in [0.001, 0.002, 0.003, 0.01]:
        metrics.observe("llm_call", s)
    snap = metrics.snapshot()
    t = snap["timers"]["llm_call"]
    assert t["count"] == 4
    assert t["max_ms"] >= t["p50_ms"]
    assert t["avg_ms"] > 0


def test_tracer_records_error_propagates():
    """span 内异常仍向上抛。"""
    with pytest.raises(ValueError):
        with span("fails"):
            raise ValueError("boom")


# ---- LLM-judge 测试 ----


class _StubJudgeLLM:
    """返回固定 JSON 评分的 stub LLM。"""

    def __init__(self, raw: str):
        self._raw = raw
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        return self._raw


@pytest.mark.asyncio
async def test_eval_llm_judge_with_mock_llm(monkeypatch):
    """启用 EVALS_LLM_JUDGE 后，mock LLM 返回的分数落到 CaseResult 与 eval_results。"""
    from app.evals.runner import EvalRunner
    from app.evals.metrics import llm_judge

    # stub：correctness 给 0.9，groundedness 给 0.8（按调用顺序）
    seq = [
        '{"score": 0.9, "comment": "ok"}',
        '{"score": 0.8, "comment": "grounded"}',
    ]

    class _SeqLLM:
        def __init__(self):
            self.i = 0

        async def generate(self, messages, **kwargs):
            r = seq[self.i]
            self.i += 1
            return r

    from app.configs.settings import settings

    monkeypatch.setattr(settings, "EVALS_LLM_JUDGE", True)
    # 直接构造 runner，judge_llm 非空即启用
    runner = EvalRunner(db=None, judge_llm=_SeqLLM())
    assert runner.llm_judge_enabled

    async def fake_run(query):
        return ("要约与承诺是合同订立的核心", ["要约与承诺的规则"], 5.0)

    results = await runner.run("legal/legal_basic", fake_run)
    assert results[0].llm_correctness == pytest.approx(0.9)
    assert results[0].llm_groundedness == pytest.approx(0.8)


def test_llm_judge_parse_score_fence():
    """LLM 输出带 ```json fence 时仍能解析。"""
    raw = 'some prefix\n```json\n{"score": 0.75, "comment": "decent"}\n```\n'
    s, c = llm_judge._parse_score(raw)
    assert s == 0.75
    assert "decent" in c


def test_llm_judge_parse_score_clamps():
    """超界分数被 clamp 到 [0,1]。"""
    s, _ = llm_judge._parse_score('{"score": 1.5, "comment": ""}')
    assert s == 1.0
    s, _ = llm_judge._parse_score('{"score": -0.3, "comment": ""}')
    assert s == 0.0


def test_llm_judge_parse_score_invalid():
    """无效输出返回 0 分。"""
    s, c = llm_judge._parse_score("not json at all")
    assert s == 0.0
    assert c == ""
