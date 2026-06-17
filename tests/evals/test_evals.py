import pytest

from app.evals.analyzer import BadCaseAnalyzer
from app.evals.metrics.correctness import correctness_score
from app.evals.metrics.groundedness import groundedness_score
from app.evals.metrics.retrieval import retrieval_recall, context_precision
from app.evals.runner import EvalRunner, load_dataset


def test_correctness_keyword_hit():
    assert correctness_score("要约与承诺", ["要约", "承诺"]) == 1.0
    assert correctness_score("要约", ["要约", "承诺"]) == 0.5


def test_groundedness_basic():
    score = groundedness_score("要约承诺合同", ["要约承诺合同成立"])
    assert score > 0.0


def test_retrieval_recall_and_precision():
    ctx = ["要约与承诺的规则", "侵权责任"]
    assert retrieval_recall(ctx, ["要约", "承诺", "侵权"]) == 1.0
    # 2 条中 1 条含"要约" → 0.5
    assert context_precision(ctx, ["要约"]) == 0.5
    assert context_precision(ctx, ["不存在的词"]) == 0.0


def test_load_legal_dataset():
    cases = load_dataset("legal/legal_basic")
    assert len(cases) >= 1
    assert cases[0].id.startswith("legal-")


@pytest.mark.asyncio
async def test_eval_runner_with_mock_fn():
    async def fake_run(query):
        return ("要约与承诺是合同订立的核心", ["要约与承诺的规则"], 12.3)

    runner = EvalRunner(db=None)
    results = await runner.run("legal/legal_basic", fake_run)
    assert len(results) >= 1
    assert results[0].correctness > 0
    assert results[0].latency_ms == 12.3


def test_bad_case_analyzer_finds_weak_metric():
    from app.evals.runner import CaseResult

    cases = [
        CaseResult("a", "ok", 0.9, 0.8, 0.7, 0.6, 10),
        CaseResult("b", "bad", 0.2, 0.1, 0.3, 0.2, 20),
    ]
    out = BadCaseAnalyzer(threshold=0.5).analyze(cases)
    assert out["total"] == 2
    assert out["bad_case_count"] == 1
    assert out["weak_metric"] is not None
