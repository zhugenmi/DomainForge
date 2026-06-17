import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.message import Message


class MessageRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, session_id: uuid.UUID, role: str, content: str) -> Message:
        msg = Message(session_id=session_id, role=role, content=content)
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def list_by_session(self, session_id: uuid.UUID, limit: int = 50) -> list[Message]:
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
