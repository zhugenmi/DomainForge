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
        if not self.reranker.available():
            logger.info("rerank_noop", reason="no_rerank_endpoint")
            candidates = self.reranker.rerank_simple(query, docs, top_n=len(docs))
        else:
            # 真实 rerank API 调用留作扩展；当前统一走 simple 路径以避免阻塞
            candidates = self.reranker.rerank_simple(query, docs, top_n=len(docs))
        if metadata:
            for c, m in zip(candidates, metadata):
                c.metadata = m
        return candidates[:top_n]
