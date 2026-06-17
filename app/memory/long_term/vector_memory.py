from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.memory_repo import MemoryRepo
from app.llm.embedding.embedding_service import EmbeddingService
from app.observability.logging.logger import get_logger

logger = get_logger("memory.long_term")


class VectorMemory:
    """长期记忆：用户偏好与事实，写入 memories 表并附带 embedding，支持向量召回。"""

    def __init__(
        self,
        db: AsyncSession,
        embedder: EmbeddingService,
        user_id: uuid.UUID,
        repo: MemoryRepo | None = None,
    ):
        self.db = db
        self.embedder = embedder
        self.user_id = user_id
        self.repo = repo or MemoryRepo(db)

    async def remember(self, content: str, metadata: dict | None = None) -> None:
        if not content:
            return
        emb = await self.embedder.embed_one(content)
        await self.repo.create(
            user_id=self.user_id,
            memory_type="long_term",
            content=content,
            embedding=emb,
            metadata=metadata or {},
        )

    async def recall(self, query: str, top_k: int = 3) -> list[str]:
        emb = await self.embedder.embed_one(query)
        mems = await self.repo.vector_search(self.user_id, emb, top_k=top_k)
        return [m.content for m in mems]

    async def list_all(self, limit: int = 50) -> list[str]:
        mems = await self.repo.list_by_user(self.user_id, memory_type="long_term", limit=limit)
        return [m.content for m in mems]


__all__ = ["VectorMemory"]
