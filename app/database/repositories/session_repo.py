import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.session import Session


class SessionRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: uuid.UUID, title: str = "New Session") -> Session:
        session = Session(user_id=user_id, title=title)
        self.db.add(session)
        await self.db.flush()
        return session

    async def get(self, session_id: uuid.UUID) -> Session | None:
        return await self.db.get(Session, session_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Session]:
        result = await self.db.execute(select(Session).where(Session.user_id == user_id))
        return list(result.scalars().all())
