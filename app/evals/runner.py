from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
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
    llm_correctness: float = 0.0
    llm_groundedness: float = 0.0


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
    def __init__(
        self,
        db: AsyncSession | None = None,
        judge_llm: Any | None = None,
    ):
        self.db = db
        self.judge_llm = judge_llm
        self.llm_judge_enabled = settings.EVALS_LLM_JUDGE and judge_llm is not None

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

            if self.llm_judge_enabled:
                # 延迟导入避免无 judge 时也加载 llm_judge（其 import 链含 LLMProvider）
                from app.evals.metrics.llm_judge import score as llm_score

                cr.llm_correctness, _ = await llm_score(
                    self.judge_llm, c.query, answer, contexts, "correctness"
                )
                cr.llm_groundedness, _ = await llm_score(
                    self.judge_llm, c.query, answer, contexts, "groundedness"
                )

            results.append(cr)
            if self.db is not None:
                await self._persist(dataset_name, cr)
            logger.info(
                "eval_case",
                dataset=dataset_name,
                case=c.id,
                correctness=cr.correctness,
                llm_correctness=cr.llm_correctness,
            )
        return results

    async def _persist(self, dataset: str, cr: CaseResult) -> None:
        pairs = [
            ("correctness", cr.correctness),
            ("groundedness", cr.groundedness),
            ("retrieval_recall", cr.retrieval_recall),
            ("context_precision", cr.context_precision),
            ("latency_ms", cr.latency_ms),
        ]
        if self.llm_judge_enabled:
            pairs.append(("llm_correctness", cr.llm_correctness))
            pairs.append(("llm_groundedness", cr.llm_groundedness))
        for metric, score_val in pairs:
            self.db.add(  # type: ignore[union-attr]
                EvalResult(
                    dataset_name=dataset,
                    metric=metric,
                    score=float(score_val),
                    payload={"case_id": cr.case_id},
                )
            )
        await self.db.flush()  # type: ignore[union-attr]


__all__ = ["EvalRunner", "EvalCase", "CaseResult", "load_dataset", "DATASET_DIR"]
