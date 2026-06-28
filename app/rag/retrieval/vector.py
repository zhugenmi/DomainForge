from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.database.repositories.document_repo import DocumentRepo
from app.llm.base import LLMProvider
from app.llm.providers.openai import OpenAIProvider


class VectorRetriever:
    def __init__(self, db: AsyncSession, llm: LLMProvider | OpenAIProvider, repo: DocumentRepo | None = None):
        self.db = db
        self.repo = repo or DocumentRepo(db)
        self.llm = llm

    async def search(self, query: str, top_k: int = 5, domain: str | None = None) -> list[DocumentChunk]:
        embeddings = await self.llm.embed([query])
        query_embedding = embeddings[0]
        chunks = await self.repo.vector_search(query_embedding, top_k=top_k, domain=domain)
        # 检索结果只读快照，从 session 分离，避免写检索/rerank 分数时被 dirty tracking 持久化进 DB
        for c in chunks:
            self.db.expunge(c)
        return chunks
