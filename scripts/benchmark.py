#!/usr/bin/env python
"""对话链路基准测试：测量端到端延迟与吞吐。

用法:
    python scripts/benchmark.py --queries 20 --concurrency 4
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.api.chat import _build_runtime_for_eval  # noqa: E402
from app.runtime.state.agent_state import AgentState  # noqa: E402

SAMPLE_QUERIES = [
    "你好",
    "什么是合同？",
    "请帮我计算 2 * (3 + 4)",
    "民法典有什么基本原则？",
    "什么是货币基金？",
]


async def _one_query(db) -> float:
    runtime = await _build_runtime_for_eval(db)
    q = SAMPLE_QUERIES[int(time.time()) % len(SAMPLE_QUERIES)]
    state = AgentState(query=q)
    start = time.perf_counter()
    await runtime.run(state)
    return (time.perf_counter() - start) * 1000


async def main(args: argparse.Namespace) -> int:
    latencies: list[float] = []
    sem = asyncio.Semaphore(args.concurrency)
    total_start = time.perf_counter()

    async def _task():
        async with sem:
            async with async_session_factory() as db:
                lat = await _one_query(db)
                latencies.append(lat)

    tasks = [asyncio.create_task(_task()) for _ in range(args.queries)]
    await asyncio.gather(*tasks)
    total = time.perf_counter() - total_start

    print(f"\n=== Benchmark ===")
    print(f"查询数: {len(latencies)}")
    print(f"并发: {args.concurrency}")
    print(f"总耗时: {total:.2f} s")
    print(f"吞吐: {len(latencies) / total:.2f} req/s")
    print(f"平均延迟: {statistics.mean(latencies):.1f} ms")
    print(f"中位数: {statistics.median(latencies):.1f} ms")
    print(f"P95: {statistics.quantiles(latencies, n=20)[-1]:.1f} ms")
    print(f"最大: {max(latencies):.1f} ms")
    print(f"最小: {min(latencies):.1f} ms")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="对话链路基准测试")
    p.add_argument("--queries", type=int, default=20)
    p.add_argument("--concurrency", type=int, default=4)
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
