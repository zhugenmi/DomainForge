from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.database.repositories.document_repo import DocumentRepo
from app.llm.base import LLMProvider
from app.llm.rerank.rerank_service import RerankService
from app.rag.retrieval.bm25 import BM25Retriever
from app.rag.retrieval.rrf import rrf_fuse
from app.rag.retrieval.vector import VectorRetriever


class HybridRetriever:
    """向量 + BM25 双路召回 → RRF 融合 → Rerank。"""

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMProvider,
        rerank: RerankService | None = None,
        repo: DocumentRepo | None = None,
    ):
        self.db = db
        self.vector = VectorRetriever(db=db, llm=llm, repo=repo)
        self.bm25 = BM25Retriever(db=db, repo=repo)
        self.rerank = rerank or RerankService()

    async def search(self, query: str, top_k: int = 5, rerank_top_n: int = 5) -> list[DocumentChunk]:
        vec_results = await self.vector.search(query, top_k=max(top_k * 3, 10))
        bm25_results = await self.bm25.search(query, top_k=max(top_k * 3, 10))

        vec_ids = [c.id for c in vec_results]
        bm25_ids = [c.id for c in bm25_results]
        fused = rrf_fuse({"vector": vec_ids, "bm25": bm25_ids}, top_n=max(rerank_top_n * 2, 10))

        id_to_chunk: dict = {}
        for c in vec_results:
            id_to_chunk[c.id] = c
        for c in bm25_results:
            id_to_chunk.setdefault(c.id, c)

        candidates = [id_to_chunk[r.doc_id] for r in fused if r.doc_id in id_to_chunk]
        candidates_text = [c.content for c in candidates]
        reranked = await self.rerank.rerank(query, candidates_text, top_n=rerank_top_n)

        out: list[DocumentChunk] = []
        for cand in reranked:
            # 通过文本找回 chunk
            for c in candidates:
                if c.content == cand.text:
                    c.score = cand.score
                    out.append(c)
                    break
        return out[:top_k]


__all__ = ["HybridRetriever"]
