from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.eval_result import EvalResult
from app.database.session import get_db
from app.evals.runner import EvalRunner

router = APIRouter(prefix="/evals", tags=["evals"])


class RunEvalsRequest(BaseModel):
    dataset: str  # e.g. "legal/legal_basic"


@router.post("/run")
async def run_evals(req: RunEvalsRequest, db: AsyncSession = Depends(get_db)):
    """同步执行评测。生产环境应改任务队列异步执行。"""
    from app.api.chat import _build_runtime_for_eval

    runner = EvalRunner(db=db)

    async def _run_fn(query: str):
        start = time.perf_counter()
        runtime = await _build_runtime_for_eval(db)
        from app.runtime.state.agent_state import AgentState

        state = AgentState(query=query)
        state = await runtime.run(state)
        latency = (time.perf_counter() - start) * 1000
        contexts = [d["content"] for d in state.retrieved_docs]
        return state.final_answer or "", contexts, latency

    try:
        results = await runner.run(req.dataset, _run_fn)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {
        "dataset": req.dataset,
        "total": len(results),
        "results": [
            {
                "case_id": r.case_id,
                "correctness": r.correctness,
                "groundedness": r.groundedness,
                "retrieval_recall": r.retrieval_recall,
                "context_precision": r.context_precision,
                "latency_ms": r.latency_ms,
            }
            for r in results
        ],
    }


@router.get("/results")
async def list_results(dataset: str | None = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    stmt = select(EvalResult).order_by(EvalResult.created_at.desc()).limit(limit)
    if dataset:
        stmt = stmt.where(EvalResult.dataset_name == dataset)
    result = await db.execute(stmt)
    return [
        {
            "id": str(r.id),
            "dataset_name": r.dataset_name,
            "metric": r.metric,
            "score": r.score,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.scalars().all()
    ]
