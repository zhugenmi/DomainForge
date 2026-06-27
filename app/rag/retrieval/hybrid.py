from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.database.repositories.document_repo import DocumentRepo
from app.llm.base import LLMProvider
from app.llm.rerank.rerank_service import RerankService
from app.rag.retrieval.bm25 import BM25Retriever
from app.rag.retrieval.query_rewriter import QueryRewriter
from app.rag.retrieval.rrf import rrf_fuse
from app.rag.retrieval.vector import VectorRetriever


class HybridRetriever:
    """向量 + BM25 双路召回 → RRF 融合 → Rerank。

    支持查询改写（指代消解 + 子查询分解）：复杂查询先改写为多个子查询，
    每个子查询各跑双路召回，结果合并后再 RRF。
    """

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMProvider,
        rerank: RerankService | None = None,
        repo: DocumentRepo | None = None,
        rewriter: QueryRewriter | None = None,
    ):
        self.db = db
        self.vector = VectorRetriever(db=db, llm=llm, repo=repo)
        self.bm25 = BM25Retriever(db=db, repo=repo)
        self.rerank = rerank or RerankService()
        self.rewriter = rewriter or QueryRewriter(llm=llm)

    async def search(
        self, query: str, top_k: int = 5, rerank_top_n: int = 5, domain: str | None = None
    ) -> list[DocumentChunk]:
        rewrites = await self.rewriter.rewrite(query)

        # 每个子查询各跑双路召回，结果按 chunk id 去重合并
        id_to_chunk: dict = {}
        vec_ranked_per_rewrite: list[list] = []
        bm25_ranked_per_rewrite: list[list] = []
        for sub in rewrites:
            vec_results = await self.vector.search(sub, top_k=max(top_k * 3, 10), domain=domain)
            bm25_results = await self.bm25.search(sub, top_k=max(top_k * 3, 10), domain=domain)
            for c in vec_results:
                id_to_chunk.setdefault(c.id, c)
            for c in bm25_results:
                id_to_chunk.setdefault(c.id, c)
            vec_ranked_per_rewrite.append([c.id for c in vec_results])
            bm25_ranked_per_rewrite.append([c.id for c in bm25_results])

        # 多子查询的 ranked list 一起喂给 RRF（source 名区分）
        ranked_lists: dict[str, list] = {}
        for i, ids in enumerate(vec_ranked_per_rewrite):
            ranked_lists[f"vector_{i}"] = ids
        for i, ids in enumerate(bm25_ranked_per_rewrite):
            ranked_lists[f"bm25_{i}"] = ids
        fused = rrf_fuse(ranked_lists, top_n=max(rerank_top_n * 2, 10))

        candidates = [id_to_chunk[r.doc_id] for r in fused if r.doc_id in id_to_chunk]
        candidates_text = [c.content for c in candidates]
        reranked = await self.rerank.rerank(query, candidates_text, top_n=rerank_top_n)

        out: list[DocumentChunk] = []
        for cand in reranked:
            for c in candidates:
                if c.content == cand.text:
                    c.score = cand.score
                    out.append(c)
                    break
        return out[:top_k]


__all__ = ["HybridRetriever"]
