from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.llm.base import LLMProvider
from app.llm.rerank.rerank_service import RerankService
from app.observability.logging.logger import get_logger
from app.rag.retrieval.bm25 import BM25Retriever
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.vector import VectorRetriever
from app.services.cache import cache_clear_prefix, cache_get, cache_set

logger = get_logger("rag.service")

RetrievalMode = Literal["vector", "bm25", "hybrid"]

_RAG_CACHE_TTL = 900  # 15 分钟


class RAGService:
    def __init__(
        self,
        db: AsyncSession,
        retriever: VectorRetriever | None = None,
        llm: LLMProvider | None = None,
        mode: RetrievalMode = "hybrid",
    ):
        self.db = db
        self.retriever = retriever
        self.llm = llm
        self.mode = mode

    def _ensure_vector(self) -> VectorRetriever:
        if self.retriever is None:
            if self.llm is None:
                raise ValueError("llm is required when retriever not provided")
            self.retriever = VectorRetriever(db=self.db, llm=self.llm)
        return self.retriever

    async def search(
        self,
        query: str,
        top_k: int = 5,
        mode: RetrievalMode | None = None,
        domain: str | None = None,
    ) -> list[DocumentChunk]:
        m = mode or self.mode
        # 检索结果缓存：Redis 可用时命中直接返回，避免重复管线
        cached = await cache_get("rag", m, str(top_k), domain or "", query)
        if cached is not None:
            logger.info("rag_cache_hit", mode=m, top_k=top_k, domain=domain)
            return [_dict_to_chunk(c) for c in cached]

        if m == "vector":
            results = await self._ensure_vector().search(query, top_k=top_k, domain=domain)
        elif m == "bm25":
            results = await BM25Retriever(self.db).search(query, top_k=top_k, domain=domain)
        elif m == "hybrid":
            if self.llm is None:
                results = await BM25Retriever(self.db).search(query, top_k=top_k, domain=domain)
            else:
                hybrid = HybridRetriever(db=self.db, llm=self.llm, rerank=RerankService())
                results = await hybrid.search(query, top_k=top_k, domain=domain)
        else:
            raise ValueError(f"unknown mode: {m}")

        await cache_set(
            "rag", [_chunk_to_dict(c) for c in results], _RAG_CACHE_TTL, m, str(top_k), domain or "", query
        )
        return results

    @staticmethod
    async def invalidate_cache() -> int:
        """知识库变更时调用，清除所有检索缓存。"""
        return await cache_clear_prefix("rag:")


def _chunk_to_dict(c: DocumentChunk) -> dict:
    return {
        "id": str(c.id),
        "document_id": str(c.document_id),
        "content": c.content,
        "metadata_": c.metadata_,
        "score": getattr(c, "score", None),
    }


def _dict_to_chunk(d: dict) -> DocumentChunk:
    import uuid

    c = DocumentChunk(
        id=uuid.UUID(d["id"]),
        document_id=uuid.UUID(d["document_id"]),
        content=d["content"],
        metadata_=d.get("metadata_") or {},
    )
    if d.get("score") is not None:
        c.score = float(d["score"])
    return c


__all__ = ["RAGService", "RetrievalMode"]
