from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.configs.settings import settings
from app.llm.rerank.bge_reranker import RerankCandidate, BGEReranker
from app.observability.logging.logger import get_logger

logger = get_logger("reranker.qwen")


class QwenReranker:
    """阿里云百炼 DashScope 原生 rerank 适配。

    与 BGEReranker 的区别：DashScope 原生 rerank 端点
    `.../api/v1/services/rerank/text-rerank/text-rerank` 要求**扁平请求体**
    （query/documents/top_n 在顶层），嵌套 `{input, parameters}` 会被拒为
    400 "Field required: input.query"。响应用 `results[].relevance_score`。

    BGE 兼容格式（`{base}/rerank` 平铺体 + `results[].score`）在 DashScope host
    上不存在该路径（404），故 qwen3-rerank 需走本模块而非 BGEReranker。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 10.0,
    ):
        self.api_key = api_key or settings.RERANK_API_KEY
        self.base_url = base_url or settings.RERANK_BASE_URL
        self.model = model or settings.RERANK_MODEL
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _native_url(self) -> str:
        root = self.base_url
        for suffix in ("/compatible-mode/v1", "/compatible-mode"):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
                break
        return root.rstrip("/") + "/api/v1/services/rerank/text-rerank/text-rerank"

    async def rerank(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        if not docs:
            return []
        url = self._native_url()
        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": top_n,
            "return_documents": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        scored: list[RerankCandidate] = []
        results = data.get("results") if isinstance(data, dict) else None
        if isinstance(results, list):
            for item in results:
                idx = item.get("index")
                score = float(item.get("relevance_score", item.get("score", 0.0)))
                if idx is not None and 0 <= idx < len(docs):
                    scored.append(RerankCandidate(text=docs[idx], score=score, index=idx))
        if not scored:
            raise ValueError(f"unexpected rerank response shape: {type(data)}")
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]

    def rerank_simple(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        # 复用 BGEReranker 的关键词重叠退路，保证链路不阻塞
        return BGEReranker.rerank_simple(self, query, docs, top_n=top_n)


__all__ = ["QwenReranker"]
