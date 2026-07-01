#!/usr/bin/env python
"""RAG 子系统评测：直调 HybridRetriever，隔离检索+Rerank 质量。

三层指标：
  Tier 1   检索质量：Recall@5/@10、MRR@10、NDCG@5、Context Precision@5
  Tier 1.5 Rerank A/B：RRF-only（identity reranker）vs RRF+Rerank 的 MRR/NDCG 差值
  Tier 3   引用定位完整率：make_citations 产物中 locator 非空、legal chapter 非空的比例

用法（需先导入语料）:
    python scripts/build_index.py --dir data/raw_documents/legal --domain legal --strategy legal
    python scripts/build_index.py --dir data/raw_documents/finance --domain finance --strategy finance
    python scripts/run_rag_eval.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.session import async_session_factory  # noqa: E402
from app.llm.providers.openai import OpenAIProvider  # noqa: E402
from app.llm.rerank.bge_reranker import RerankCandidate  # noqa: E402
from app.llm.rerank.rerank_service import RerankService  # noqa: E402
from app.rag.context.citation import make_citations  # noqa: E402
from app.rag.retrieval.hybrid import HybridRetriever  # noqa: E402

DATASET_DIR = Path(__file__).resolve().parent.parent / "app" / "evals" / "datasets"
TOP_K = 10  # 取 10 条以便计算 @5/@10


class IdentityRerank:
    """RRF-only 基线：不做任何重排，按 RRF 原顺序返回。"""

    async def rerank(self, query: str, docs: list[str], top_n: int = 5, metadata=None):
        n = min(top_n, len(docs))
        return [RerankCandidate(text=docs[i], score=0.0, index=i) for i in range(n)]


@dataclass
class CaseGold:
    id: str
    query: str
    domain: str
    gold_substrings: list[str]


def load_cases(name: str) -> list[CaseGold]:
    path = DATASET_DIR / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        CaseGold(
            id=d["id"],
            query=d["query"],
            domain=d["domain"],
            gold_substrings=d["gold_substrings"],
        )
        for d in data
    ]


def _is_relevant(chunk, gold: list[str]) -> bool:
    content = getattr(chunk, "content", "") or ""
    return any(g in content for g in gold)


def recall_at(chunks, gold: list[str], k: int) -> float:
    """单 gold 子串：top-k 命中即为 1.0；多 gold：命中子串比例。"""
    if not gold:
        return 1.0
    top = chunks[:k]
    hit = sum(1 for g in gold if any(g in (c.content or "") for c in top))
    return hit / len(gold)


def mrr_at(chunks, gold: list[str], k: int) -> float:
    for i, c in enumerate(chunks[:k], start=1):
        if _is_relevant(c, gold):
            return 1.0 / i
    return 0.0


def ndcg_at(chunks, gold: list[str], k: int) -> float:
    """二值相关性 NDCG@k。"""
    dcg = 0.0
    for i, c in enumerate(chunks[:k], start=1):
        if _is_relevant(c, gold):
            dcg += 1.0 / math.log2(i + 1)
    idcg = 1.0  # 单一相关项理想情况下排第 1
    return dcg / idcg if idcg else 0.0


def context_precision_at(chunks, gold: list[str], k: int) -> float:
    top = chunks[:k]
    if not top:
        return 0.0
    relevant = sum(1 for c in top if _is_relevant(c, gold))
    return relevant / len(top)


async def run_arm(hybrid: HybridRetriever, case: CaseGold) -> list:
    return await hybrid.search(case.query, top_k=TOP_K, rerank_top_n=TOP_K, domain=case.domain)


async def main(_: argparse.Namespace) -> int:
    llm = OpenAIProvider()
    cases = load_cases("legal/legal_rag") + load_cases("finance/finance_rag")

    per_case: list[dict] = []
    # 聚合容器
    arms = ["rrf_only", "rrf_rerank"]
    agg = {
        a: {"recall5": [], "recall10": [], "mrr10": [], "ndcg5": [], "cp5": []}
        for a in arms
    }
    citation_locator_filled = 0
    citation_total = 0
    citation_legal_chapter_filled = 0
    citation_legal_total = 0

    async with async_session_factory() as db:
        hybrid_real = HybridRetriever(db=db, llm=llm, rerank=RerankService())
        hybrid_identity = HybridRetriever(db=db, llm=llm, rerank=IdentityRerank())

        for case in cases:
            rrf_only = await run_arm(hybrid_identity, case)
            rrf_rerank = await run_arm(hybrid_real, case)

            row = {"id": case.id, "domain": case.domain, "query": case.query}
            for arm_name, chunks in [("rrf_only", rrf_only), ("rrf_rerank", rrf_rerank)]:
                r5 = recall_at(chunks, case.gold_substrings, 5)
                r10 = recall_at(chunks, case.gold_substrings, 10)
                mrr = mrr_at(chunks, case.gold_substrings, 10)
                nd = ndcg_at(chunks, case.gold_substrings, 5)
                cp = context_precision_at(chunks, case.gold_substrings, 5)
                row[f"{arm_name}_r5"] = r5
                row[f"{arm_name}_mrr"] = mrr
                row[f"{arm_name}_ndcg"] = nd
                agg[arm_name]["recall5"].append(r5)
                agg[arm_name]["recall10"].append(r10)
                agg[arm_name]["mrr10"].append(mrr)
                agg[arm_name]["ndcg5"].append(nd)
                agg[arm_name]["cp5"].append(cp)

            # Tier 3：引用定位完整率（基于生产 top_k=5 切片）
            top5 = rrf_rerank[:5]
            chunks_as_dict = [
                {
                    "id": str(c.id),
                    "document_id": str(c.document_id),
                    "content": c.content,
                    "metadata": c.metadata_ or {},
                }
                for c in top5
            ]
            cites = make_citations(chunks_as_dict)
            for c in cites:
                citation_total += 1
                if c.locator and c.locator != "相关段落":
                    citation_locator_filled += 1
                if case.domain == "legal":
                    citation_legal_total += 1
                    if c.chapter:
                        citation_legal_chapter_filled += 1

            per_case.append(row)
            print(
                f"[{case.id}] {case.query}  "
                f"rrf_only: R@5={row['rrf_only_r5']:.2f} MRR={row['rrf_only_mrr']:.2f} NDCG@5={row['rrf_only_ndcg']:.2f}  "
                f"rrf_rerank: R@5={row['rrf_rerank_r5']:.2f} MRR={row['rrf_rerank_mrr']:.2f} NDCG@5={row['rrf_rerank_ndcg']:.2f}"
            )

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print("\n=== 聚合（mean over {} cases） ===".format(len(per_case)))
    print(f"{'指标':<20}{'RRF-only':>12}{'RRF+Rerank':>14}{'Δ(lift)':>10}")
    for key, label in [
        ("recall5", "Recall@5"),
        ("recall10", "Recall@10"),
        ("mrr10", "MRR@10"),
        ("ndcg5", "NDCG@5"),
        ("cp5", "CtxPrecision@5"),
    ]:
        a = mean(agg["rrf_only"][key])
        b = mean(agg["rrf_rerank"][key])
        print(f"{label:<20}{a:>12.3f}{b:>14.3f}{b - a:>10.3f}")

    print("\n=== Tier 3 引用定位完整率 ===")
    print(f"locator 非空率: {citation_locator_filled}/{citation_total} = "
          f"{citation_locator_filled / citation_total:.3f}" if citation_total else "n/a")
    if citation_legal_total:
        print(f"legal chapter 非空率: {citation_legal_chapter_filled}/{citation_legal_total} = "
              f"{citation_legal_chapter_filled / citation_legal_total:.3f}")

    # 逐 case 明细便于核对
    print("\n=== 逐 case 明细 ===")
    for r in per_case:
        print(
            f"{r['id']}  domain={r['domain']}\n"
            f"  query: {r['query']}\n"
            f"  rrf_only   R@5={r['rrf_only_r5']:.2f} MRR@10={r['rrf_only_mrr']:.2f} NDCG@5={r['rrf_only_ndcg']:.2f}\n"
            f"  rrf_rerank R@5={r['rrf_rerank_r5']:.2f} MRR@10={r['rrf_rerank_mrr']:.2f} NDCG@5={r['rrf_rerank_ndcg']:.2f}"
        )
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RAG 子系统评测")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
