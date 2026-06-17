#!/usr/bin/env python
"""执行评测数据集并打印报告。

用法:
    python scripts/run_evals.py --dataset legal/legal_basic
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.evals.analyzer import BadCaseAnalyzer  # noqa: E402
from app.evals.runner import EvalRunner  # noqa: E402
from app.api.chat import _build_runtime_for_eval  # noqa: E402
from app.runtime.state.agent_state import AgentState  # noqa: E402


async def _run_fn_factory(db):
    async def _run(query: str):
        start = time.perf_counter()
        runtime = await _build_runtime_for_eval(db)
        state = AgentState(query=query)
        state = await runtime.run(state)
        latency = (time.perf_counter() - start) * 1000
        contexts = [d["content"] for d in state.retrieved_docs]
        return state.final_answer or "", contexts, latency

    return _run


async def main(args: argparse.Namespace) -> int:
    async with async_session_factory() as db:
        runner = EvalRunner(db=db)
        run_fn = await _run_fn_factory(db)
        try:
            results = await runner.run(args.dataset, run_fn)
        except FileNotFoundError as e:
            print(f"[error] {e}")
            return 1
        await db.commit()

    report = BadCaseAnalyzer(threshold=0.5).analyze(results)
    print(f"\n=== 评测报告: {args.dataset} ===")
    print(f"用例总数: {report['total']}")
    print(f"Bad case 数: {report['bad_case_count']}")
    print(f"平均指标:")
    for k, v in report["averages"].items():
        print(f"  {k}: {v:.3f}")
    print(f"平均延迟: {report['avg_latency_ms']:.1f} ms")
    print(f"最弱指标: {report['weak_metric']}")
    if report["bad_cases"]:
        print("\nBad Cases:")
        for bc in report["bad_cases"]:
            print(f"  - {bc['case_id']}: correctness={bc['correctness']:.3f}")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="执行评测")
    p.add_argument("--dataset", required=True, help="数据集名，如 legal/legal_basic")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
