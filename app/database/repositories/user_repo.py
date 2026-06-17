import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.user import User


class UserRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, username: str, role: str = "user") -> User:
        user = User(username=username, role=role)
        self.db.add(user)
        await self.db.flush()
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100) -> list[User]:
        result = await self.db.execute(select(User).limit(limit))
        return list(result.scalars().all())

    async def get_or_create_default(self) -> User:
        default_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        user = await self.get(default_id)
        if user is None:
            user = User(id=default_id, username="anonymous", role="admin")
            self.db.add(user)
            await self.db.flush()
        return user
