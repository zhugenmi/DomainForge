from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.llm.base import LLMProvider
from app.llm.rerank.rerank_service import RerankService
from app.rag.retrieval.bm25 import BM25Retriever
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.vector import VectorRetriever

RetrievalMode = Literal["vector", "bm25", "hybrid"]


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

    async def search(self, query: str, top_k: int = 5, mode: RetrievalMode | None = None) -> list[DocumentChunk]:
        m = mode or self.mode
        if m == "vector":
            return await self._ensure_vector().search(query, top_k=top_k)
        if m == "bm25":
            return await BM25Retriever(self.db).search(query, top_k=top_k)
        if m == "hybrid":
            if self.llm is None:
                return await BM25Retriever(self.db).search(query, top_k=top_k)
            hybrid = HybridRetriever(db=self.db, llm=self.llm, rerank=RerankService())
            return await hybrid.search(query, top_k=top_k)
        raise ValueError(f"unknown mode: {m}")


__all__ = ["RAGService", "RetrievalMode"]
