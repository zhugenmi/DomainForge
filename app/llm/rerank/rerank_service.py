from __future__ import annotations

from app.configs.settings import settings
from app.llm.rerank.bge_reranker import BGEReranker, RerankCandidate
from app.llm.rerank.qwen_reranker import QwenReranker
from app.observability.logging.logger import get_logger

logger = get_logger("rerank")

# 两种 reranker 共同接口：available() / rerank() / rerank_simple()
Reranker = BGEReranker | QwenReranker


def _select_default_reranker() -> Reranker:
    """按 settings.RERANK_MODEL 选择 reranker 实现。

    qwen3-rerank 等 DashScope 模型走 QwenReranker（扁平体原生端点）；
    bge-reranker-* 等 BGE 兼容模型走 BGEReranker。
    """
    model = (settings.RERANK_MODEL or "").lower()
    if "qwen" in model:
        return QwenReranker()
    return BGEReranker()


class RerankService:
    def __init__(self, reranker: Reranker | None = None):
        self.reranker = reranker or _select_default_reranker()

    async def rerank(
        self,
        query: str,
        docs: list[str],
        top_n: int = 5,
        metadata: list[dict] | None = None,
    ) -> list[RerankCandidate]:
        if not docs:
            return []
        if self.reranker.available():
            try:
                candidates = await self.reranker.rerank(query, docs, top_n=len(docs))
                logger.info("rerank_real", candidates=len(candidates))
            except Exception as e:
                logger.warning("rerank_api_failed", error=str(e), fallback="simple")
                candidates = self.reranker.rerank_simple(query, docs, top_n=len(docs))
        else:
            logger.info("rerank_noop", reason="no_rerank_endpoint")
            candidates = self.reranker.rerank_simple(query, docs, top_n=len(docs))
        if metadata:
            for c, m in zip(candidates, metadata):
                c.metadata = m
        return candidates[:top_n]
