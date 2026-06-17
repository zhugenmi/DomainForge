from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.message_repo import MessageRepo
from app.database.models.message import Message


class BufferMemory:
    def __init__(self, db: AsyncSession, session_id: uuid.UUID, max_messages: int = 20):
        self.db = db
        self.session_id = session_id
        self.max_messages = max_messages
        self._repo = MessageRepo(db)

    async def add(self, role: str, content: str) -> Message:
        return await self._repo.create(self.session_id, role, content)

    async def get_messages(self) -> list[Message]:
        return await self._repo.list_by_session(self.session_id, limit=self.max_messages)

    async def get_context(self) -> list[dict[str, str]]:
        messages = await self.get_messages()
        return [{"role": m.role, "content": m.content} for m in messages]
