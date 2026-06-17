import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import Memory


class MemoryRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: uuid.UUID,
        memory_type: str,
        content: str,
        session_id: uuid.UUID | None = None,
        embedding: list[float] | None = None,
        metadata: dict | None = None,
    ) -> Memory:
        mem = Memory(
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=content,
            embedding=embedding,
            metadata_=metadata or {},
        )
        self.db.add(mem)
        await self.db.flush()
        return mem

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        memory_type: str | None = None,
        limit: int = 50,
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.user_id == user_id)
        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)
        stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_session(
        self, session_id: uuid.UUID, memory_type: str | None = None
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.session_id == session_id)
        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)
        stmt = stmt.order_by(Memory.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def vector_search(
        self, user_id: uuid.UUID, query_embedding: list[float], top_k: int = 5
    ) -> list[Memory]:
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .where(Memory.memory_type == "long_term")
            .where(Memory.embedding.isnot(None))
            .order_by(Memory.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
