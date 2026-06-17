from __future__ import annotations

from app.configs.settings import settings
from app.llm.base import LLMProvider
from app.llm.providers.openai import OpenAIProvider
from app.observability.metrics.metrics import metrics


class EmbeddingService:
    """统一 embedding 入口，封装批量与缓存策略。"""

    def __init__(self, llm: LLMProvider | None = None, batch_size: int | None = None):
        self.llm = llm or OpenAIProvider()
        # 默认用 settings.EMBEDDING_BATCH_SIZE；部分厂商（如 DashScope）限制单批 ≤10
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        with metrics.time("embedding.total"):
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                vecs = await self.llm.embed(batch)
                out.extend(vecs)
                metrics.inc("embedding.docs", len(batch))
        return out

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed([text])
        return vecs[0]
