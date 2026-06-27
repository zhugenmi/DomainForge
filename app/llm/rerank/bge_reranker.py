from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from app.observability.logging.logger import get_logger

logger = get_logger("reranker")


@dataclass
class RerankCandidate:
    text: str
    score: float = 0.0
    metadata: dict | None = None


class BGEReranker:
    """BGE-Reranker 适配。

    优先调真实 rerank HTTP API（配置 RERANK_BASE_URL + RERANK_API_KEY 时）；
    失败或未配置时退化为基于关键词重叠的 `rerank_simple`，保证链路不阻塞。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "bge-reranker-base",
        timeout: float = 3.0,
    ):
        self.api_key = api_key or os.getenv("RERANK_API_KEY", "")
        self.base_url = base_url or os.getenv("RERANK_BASE_URL", "")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    async def rerank(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        """调真实 rerank API。响应格式兼容两种常见约定：
        - {"results": [{"index": int, "score": float}, ...]}
        - {"scores": [float, ...]}  （按 docs 顺序）
        """
        if not docs:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {"model": self.model, "query": query, "documents": docs, "top_n": top_n}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/rerank", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        scored: list[RerankCandidate] = []
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            for item in data["results"]:
                idx = item.get("index")
                score = float(item.get("score", 0.0))
                if idx is not None and 0 <= idx < len(docs):
                    scored.append(RerankCandidate(text=docs[idx], score=score))
        elif isinstance(data, dict) and isinstance(data.get("scores"), list):
            for idx, score in enumerate(data["scores"]):
                if idx < len(docs):
                    scored.append(RerankCandidate(text=docs[idx], score=float(score)))
        else:
            raise ValueError(f"unexpected rerank response shape: {type(data)}")

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]

    def rerank_simple(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        """关键词重叠打分，无外部依赖的退路。"""
        q_tokens = set(query.lower().split())
        scored: list[RerankCandidate] = []
        for d in docs:
            tokens = set(d.lower().split())
            overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
            scored.append(RerankCandidate(text=d, score=overlap))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]


__all__ = ["BGEReranker", "RerankCandidate"]
