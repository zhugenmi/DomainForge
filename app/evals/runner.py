from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.eval_result import EvalResult
from app.evals.metrics.correctness import correctness_score
from app.evals.metrics.groundedness import groundedness_score
from app.evals.metrics.retrieval import retrieval_recall, context_precision
from app.observability.logging.logger import get_logger

logger = get_logger("evals.runner")

DATASET_DIR = Path(__file__).parent / "datasets"


@dataclass
class EvalCase:
    id: str
    query: str
    expected_keywords: list[str]
    expected_answer_keywords: list[str] = field(default_factory=list)


@dataclass
class CaseResult:
    case_id: str
    answer: str
    correctness: float
    groundedness: float
    retrieval_recall: float
    context_precision: float
    latency_ms: float


def load_dataset(name: str) -> list[EvalCase]:
    """name 形如 'legal/legal_basic'。"""
    path = DATASET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalCase(
            id=d["id"],
            query=d["query"],
            expected_keywords=d.get("expected_keywords", []),
            expected_answer_keywords=d.get("expected_answer_keywords", []),
        )
        for d in data
    ]


# 调用方注入的执行函数：query -> (answer, retrieved_contexts, latency_ms)
RunFn = Callable[[str], Awaitable[tuple[str, list[str], float]]]


class EvalRunner:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def run(self, dataset_name: str, run_fn: RunFn) -> list[CaseResult]:
        cases = load_dataset(dataset_name)
        results: list[CaseResult] = []
        for c in cases:
            answer, contexts, latency_ms = await run_fn(c.query)
            cr = CaseResult(
                case_id=c.id,
                answer=answer,
                correctness=correctness_score(answer, c.expected_answer_keywords or c.expected_keywords),
                groundedness=groundedness_score(answer, contexts),
                retrieval_recall=retrieval_recall(contexts, c.expected_keywords),
                context_precision=context_precision(contexts, c.expected_keywords),
                latency_ms=latency_ms,
            )
            results.append(cr)
            if self.db is not None:
                await self._persist(dataset_name, cr)
            logger.info("eval_case", dataset=dataset_name, case=c.id, correctness=cr.correctness)
        return results

    async def _persist(self, dataset: str, cr: CaseResult) -> None:
        for metric, score in [
            ("correctness", cr.correctness),
            ("groundedness", cr.groundedness),
            ("retrieval_recall", cr.retrieval_recall),
            ("context_precision", cr.context_precision),
            ("latency_ms", cr.latency_ms),
        ]:
            self.db.add(  # type: ignore[union-attr]
                EvalResult(
                    dataset_name=dataset,
                    metric=metric,
                    score=float(score),
                    payload={"case_id": cr.case_id},
                )
            )
        await self.db.flush()  # type: ignore[union-attr]


__all__ = ["EvalRunner", "EvalCase", "CaseResult", "load_dataset", "DATASET_DIR"]
