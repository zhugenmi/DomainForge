from __future__ import annotations

from collections import defaultdict

from app.evals.runner import CaseResult


class BadCaseAnalyzer:
    """聚合 EvalRunner 结果，找出 bad case 与弱指标。"""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def analyze(self, results: list[CaseResult]) -> dict:
        if not results:
            return {"total": 0, "bad_cases": [], "weak_metric": None}
        bad = [r for r in results if r.correctness < self.threshold]
        metric_scores: dict[str, list[float]] = defaultdict(list)
        for r in results:
            metric_scores["correctness"].append(r.correctness)
            metric_scores["groundedness"].append(r.groundedness)
            metric_scores["retrieval_recall"].append(r.retrieval_recall)
            metric_scores["context_precision"].append(r.context_precision)
        avg = {k: sum(v) / len(v) for k, v in metric_scores.items()}
        weak = min(avg.items(), key=lambda x: x[1])[0] if avg else None
        return {
            "total": len(results),
            "bad_case_count": len(bad),
            "bad_cases": [{"case_id": b.case_id, "correctness": b.correctness} for b in bad],
            "averages": avg,
            "weak_metric": weak,
            "avg_latency_ms": sum(r.latency_ms for r in results) / len(results),
        }


__all__ = ["BadCaseAnalyzer"]
