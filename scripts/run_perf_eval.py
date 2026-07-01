#!/usr/bin/env python
"""DomainForge 性能评测：检索延迟 / 端到端响应时间 / Token 成本。

三项指标：
  1. 检索延迟 p50/p99    直调 HybridRetriever.search，含 vector+bm25+RRF+Rerank
  2. 端到端响应时间 p50/p99  AgentRuntime.run 完整对话链路
  3. Token 成本         monkeypatch openai 底层捕获 response.usage

用法（需先导入语料，同 phase12 §9.5）:
    python scripts/run_perf_eval.py
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.api.chat import _build_runtime_for_eval  # noqa: E402
from app.llm.providers.openai import OpenAIProvider  # noqa: E402
from app.llm.rerank.rerank_service import RerankService  # noqa: E402
from app.rag.retrieval.hybrid import HybridRetriever  # noqa: E402
from app.runtime.state.agent_state import AgentState  # noqa: E402

# 复用现有评测资产
from scripts.run_rag_eval import load_cases  # noqa: E402
from scripts.benchmark import SAMPLE_QUERIES  # noqa: E402

import openai.resources.chat.completions as _chat_mod  # noqa: E402
import openai.resources.embeddings as _embed_mod  # noqa: E402

RETRIEVAL_REPEAT = 10  # 每 query 重复次数 → 5 query × 10 = 50 样本
E2E_REPEAT = 4  # 每 query 重复次数 → 5 query × 4 = 20 样本


@dataclass
class TokenCounter:
    """累计 openai 调用的 token 用量。snapshot/restore 支持按对话切分。"""
    llm_prompt: int = 0
    llm_completion: int = 0
    embed_total: int = 0
    per_conversation: list[dict] = field(default_factory=list)

    def add_llm(self, prompt: int, completion: int) -> None:
        self.llm_prompt += prompt or 0
        self.llm_completion += completion or 0

    def add_embed(self, total: int) -> None:
        self.embed_total += total or 0

    def snapshot(self) -> tuple[int, int, int]:
        return (self.llm_prompt, self.llm_completion, self.embed_total)

    def commit_conversation(self) -> None:
        p, c, e = self.snapshot()
        self.per_conversation.append({"prompt": p, "completion": c, "embed": e})


@contextmanager
def patch_openai_usage(counter: TokenCounter):
    """monkeypatch openai 底层 create 方法，捕获 response.usage。

    覆盖 chat.completions.create（generate / chat_with_tools）与 embeddings.create（embed）。
    streaming 返回 AsyncStream 无 .usage，hasattr 守卫跳过。
    """
    orig_chat = _chat_mod.AsyncCompletions.create
    orig_embed = _embed_mod.AsyncEmbeddings.create

    async def wrapped_chat(self, *args, **kwargs):
        resp = await orig_chat(self, *args, **kwargs)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            counter.add_llm(usage.prompt_tokens, usage.completion_tokens)
        return resp

    async def wrapped_embed(self, *args, **kwargs):
        resp = await orig_embed(self, *args, **kwargs)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            counter.add_embed(usage.total_tokens)
        return resp

    _chat_mod.AsyncCompletions.create = wrapped_chat
    _embed_mod.AsyncEmbeddings.create = wrapped_embed
    try:
        yield
    finally:
        _chat_mod.AsyncCompletions.create = orig_chat
        _embed_mod.AsyncEmbeddings.create = orig_embed


def percentile(xs: list[float], p: float) -> float:
    """线性插值百分位。"""
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


async def measure_retrieval() -> list[float]:
    """直调 HybridRetriever.search，返回 RETRIEVAL_REPEAT × n_cases 个延迟样本（ms）。"""
    cases = load_cases("legal/legal_rag") + load_cases("finance/finance_rag")
    latencies: list[float] = []
    async with async_session_factory() as db:
        hybrid = HybridRetriever(db=db, llm=OpenAIProvider(), rerank=RerankService())
        for case in cases:
            for _ in range(RETRIEVAL_REPEAT):
                start = time.perf_counter()
                await hybrid.search(case.query, top_k=5, rerank_top_n=5, domain=case.domain)
                latencies.append((time.perf_counter() - start) * 1000)
    return latencies


async def measure_e2e() -> tuple[list[float], TokenCounter]:
    """运行 AgentRuntime.run，返回 E2E_REPEAT × len(SAMPLE_QUERIES) 个延迟 + token 计数。"""
    counter = TokenCounter()
    latencies: list[float] = []
    with patch_openai_usage(counter):
        for q in SAMPLE_QUERIES:
            for _ in range(E2E_REPEAT):
                async with async_session_factory() as db:
                    runtime = await _build_runtime_for_eval(db)
                    state = AgentState(query=q)
                    start = time.perf_counter()
                    await runtime.run(state)
                    latencies.append((time.perf_counter() - start) * 1000)
                    counter.commit_conversation()
    return latencies, counter


def fmt_latency(label: str, xs: list[float]) -> str:
    return (
        f"=== {label} (n={len(xs)}) ===\n"
        f"  p50: {percentile(xs, 50):.1f} ms\n"
        f"  p99: {percentile(xs, 99):.1f} ms\n"
        f"  mean: {statistics.mean(xs):.1f} ms\n"
        f"  max: {max(xs):.1f} ms\n"
        f"  min: {min(xs):.1f} ms"
    )


def fmt_tokens(counter: TokenCounter) -> str:
    convs = counter.per_conversation
    n = len(convs)
    prompts = [c["prompt"] for c in convs]
    completions = [c["completion"] for c in convs]
    embeds = [c["embed"] for c in convs]
    totals = [p + c + e for p, c, e in zip(prompts, completions, embeds)]
    return (
        f"=== Token 成本 (n={n} 对话) ===\n"
        f"  LLM prompt     均值: {statistics.mean(prompts):.0f}  "
        f"中位数: {statistics.median(prompts):.0f}  总和: {sum(prompts)}\n"
        f"  LLM completion 均值: {statistics.mean(completions):.0f}  "
        f"中位数: {statistics.median(completions):.0f}  总和: {sum(completions)}\n"
        f"  Embedding      均值: {statistics.mean(embeds):.0f}  "
        f"中位数: {statistics.median(embeds):.0f}  总和: {sum(embeds)}\n"
        f"  单次对话总 token 均值: {statistics.mean(totals):.0f}  "
        f"中位数: {statistics.median(totals):.0f}"
    )


async def main(_: argparse.Namespace) -> int:
    print("▶ 采集检索延迟（50 样本）...")
    retr = await measure_retrieval()
    print(fmt_latency("检索延迟", retr))

    print("\n▶ 采集端到端响应时间 + Token（20 样本，含真实 LLM 调用）...")
    e2e, counter = await measure_e2e()
    print(fmt_latency("端到端响应时间", e2e))
    print()
    print(fmt_tokens(counter))
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DomainForge 性能评测")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
