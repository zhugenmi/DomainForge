from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from openai import RateLimitError

from app.configs.settings import settings
from app.llm.base import LLMProvider
from app.llm.providers.openai import OpenAIProvider
from app.observability.metrics.metrics import metrics

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BASE_BACKOFF = 1.0


class EmbeddingService:
    """统一 embedding 入口，封装批量、限流与重试策略。"""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        batch_size: int | None = None,
        batch_interval: float | None = None,
        max_retries: int = _MAX_RETRIES,
    ):
        self.llm = llm or OpenAIProvider()
        # 默认用 settings.EMBEDDING_BATCH_SIZE；部分厂商（如 DashScope）限制单批 ≤10
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        # 批次间节流（秒），用于规避厂商账户级 RPM 限制（如火山方舟 429）
        self.batch_interval = (
            batch_interval if batch_interval is not None else getattr(settings, "EMBEDDING_BATCH_INTERVAL", 0.2)
        )
        self.max_retries = max_retries

    async def _embed_with_retry(self, batch: list[str]) -> list[list[float]]:
        attempt = 0
        while True:
            try:
                return await self.llm.embed(batch)
            except RateLimitError as e:
                if attempt >= self.max_retries:
                    logger.error("embedding rate-limited after %d retries: %s", attempt, e)
                    raise
                # 优先尊重 Retry-After，否则指数退避 2^n * base
                retry_after = getattr(e, "retry_after", None)
                wait = float(retry_after) if retry_after else _BASE_BACKOFF * (2 ** attempt)
                logger.warning(
                    "embedding 429 on batch (attempt %d/%d), sleeping %.1fs",
                    attempt + 1,
                    self.max_retries,
                    wait,
                )
                await asyncio.sleep(wait)
                attempt += 1

    async def embed(
        self,
        texts: list[str],
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        total = len(texts)
        with metrics.time("embedding.total"):
            for i in range(0, total, self.batch_size):
                batch = texts[i : i + self.batch_size]
                vecs = await self._embed_with_retry(batch)
                out.extend(vecs)
                metrics.inc("embedding.docs", len(batch))
                if on_progress is not None:
                    await on_progress(len(out), total)
                # 批次间节流，避免连续请求触发账户级 RPM 限制
                if self.batch_interval > 0 and i + self.batch_size < total:
                    await asyncio.sleep(self.batch_interval)
        return out

    async def embed_one(self, text: str) -> list[float]:
        vecs = await self.embed([text])
        return vecs[0]
