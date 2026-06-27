from __future__ import annotations

from app.llm.rerank.bge_reranker import BGEReranker, RerankCandidate
from app.observability.logging.logger import get_logger

logger = get_logger("rerank")


class RerankService:
    def __init__(self, reranker: BGEReranker | None = None):
        self.reranker = reranker or BGEReranker()

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
