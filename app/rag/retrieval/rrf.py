from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class RRFResult:
    doc_id: Any
    score: float
    source_ranks: dict[str, int]  # 每路召回中的名次


def rrf_fuse(
    ranked_lists: dict[str, list[Any]],
    k: int = 60,
    top_n: int | None = None,
) -> list[RRFResult]:
    """Reciprocal Rank Fusion：融合多路召回结果。

    ranked_lists: {"vector": [doc1, doc3, ...], "bm25": [doc2, doc1, ...]}
    返回融合后按分数排序的候选列表。
    """
    scores: dict[Any, float] = defaultdict(float)
    ranks: dict[Any, dict[str, int]] = defaultdict(dict)
    for source, lst in ranked_lists.items():
        for rank, doc_id in enumerate(lst):
            scores[doc_id] += 1.0 / (k + rank + 1)
            ranks[doc_id][source] = rank

    items = [RRFResult(doc_id=did, score=s, source_ranks=ranks[did]) for did, s in scores.items()]
    items.sort(key=lambda x: x.score, reverse=True)
    if top_n is not None:
        items = items[:top_n]
    return items


__all__ = ["rrf_fuse", "RRFResult"]
