from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.memory.short_term.buffer_memory import BufferMemory


class MemoryManager:
    def __init__(self, db: AsyncSession, session_id: uuid.UUID):
        self.short_term = BufferMemory(
            db=db,
            session_id=session_id,
            max_messages=settings.SHORT_TERM_MEMORY_SIZE,
        )

    async def add_message(self, role: str, content: str) -> None:
        await self.short_term.add(role, content)

    async def get_context(self) -> list[dict[str, str]]:
        return await self.short_term.get_context()
