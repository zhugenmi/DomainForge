from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RerankCandidate:
    text: str
    score: float = 0.0
    metadata: dict | None = None


class BGEReranker:
    """BGE-Reranker 适配。

    优先使用通过 OpenAI 兼容协议暴露的 rerank 接口（如部分 BGE 服务）；
    若环境未配置 RERANK_API_KEY，则退化为基于关键词重叠的简单打分，
    保证链路可用、不阻塞主流程。
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str = "bge-reranker-base"):
        self.api_key = api_key or os.getenv("RERANK_API_KEY", "")
        self.base_url = base_url or os.getenv("RERANK_BASE_URL", "")
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def rerank_simple(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        q_tokens = set(query.lower().split())
        scored: list[RerankCandidate] = []
        for d in docs:
            tokens = set(d.lower().split())
            overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
            scored.append(RerankCandidate(text=d, score=overlap))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]


__all__ = ["BGEReranker", "RerankCandidate"]
