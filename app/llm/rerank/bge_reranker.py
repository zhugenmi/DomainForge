from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.configs.settings import settings
from app.observability.logging.logger import get_logger

logger = get_logger("reranker")


@dataclass
class RerankCandidate:
    text: str
    score: float = 0.0
    metadata: dict | None = None
    index: int | None = None


class BGEReranker:
    """Rerank 适配，兼容两种后端：

    - DashScope（阿里云百炼）：base_url 形如 `.../compatible-mode/v1`，
      实际 rerank 走原生路径 `.../api/v1/services/rerank/text-rerank/text-rerank`，
      请求体嵌套 `input`/`parameters`，响应用 `relevance_score`。
    - BGE 兼容（SiliconFlow / Jina / 自部署）：`{base_url}/rerank`，平铺请求体，
      响应用 `results[].score` 或 `scores[]`。

    未配置或调用失败时退化为 `rerank_simple`（关键词重叠），保证链路不阻塞。
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

    def _is_dashscope(self) -> bool:
        u = self.base_url.lower()
        return "dashscope" in u or "maas.aliyuncs.com" in u

    def _dashscope_url(self) -> str:
        root = self.base_url
        for suffix in ("/compatible-mode/v1", "/compatible-mode"):
            if root.endswith(suffix):
                root = root[: -len(suffix)]
                break
        return root.rstrip("/") + "/api/v1/services/rerank/text-rerank/text-rerank"

    async def rerank(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        if not docs:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if self._is_dashscope():
            url = self._dashscope_url()
            payload = {
                "model": self.model,
                "input": {"query": query, "documents": docs},
                "parameters": {"top_n": top_n, "return_documents": False},
            }
        else:
            url = f"{self.base_url}/rerank"
            payload = {"model": self.model, "query": query, "documents": docs, "top_n": top_n}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        scored = self._parse_response(data, docs)
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]

    @staticmethod
    def _parse_response(data: dict, docs: list[str]) -> list[RerankCandidate]:
        """解析三种响应格式：
        - DashScope: {"output": {"results": [{"index", "relevance_score", "document": {"text"}}, ...]}}
        - BGE results: {"results": [{"index", "score"}, ...]}
        - BGE scores: {"scores": [float, ...]}  （按 docs 顺序）
        """
        scored: list[RerankCandidate] = []
        if isinstance(data, dict):
            results = data.get("output", {}).get("results") if isinstance(data.get("output"), dict) else None
            if results is None:
                results = data.get("results")
            if isinstance(results, list):
                for item in results:
                    idx = item.get("index")
                    score = float(item.get("relevance_score", item.get("score", 0.0)))
                    if idx is not None and 0 <= idx < len(docs):
                        scored.append(RerankCandidate(text=docs[idx], score=score, index=idx))
                if scored:
                    return scored
            if isinstance(data.get("scores"), list):
                for idx, score in enumerate(data["scores"]):
                    if idx < len(docs):
                        scored.append(RerankCandidate(text=docs[idx], score=float(score), index=idx))
                if scored:
                    return scored
        raise ValueError(f"unexpected rerank response shape: {type(data)}")

    def rerank_simple(self, query: str, docs: list[str], top_n: int = 5) -> list[RerankCandidate]:
        """关键词重叠打分，无外部依赖的退路。"""
        q_tokens = set(query.lower().split())
        scored: list[RerankCandidate] = []
        for idx, d in enumerate(docs):
            tokens = set(d.lower().split())
            overlap = len(q_tokens & tokens) / max(1, len(q_tokens))
            scored.append(RerankCandidate(text=d, score=overlap, index=idx))
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_n]


__all__ = ["BGEReranker", "RerankCandidate"]
