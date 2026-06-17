from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.category import Category


class CategoryRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[Category]:
        result = await self.db.execute(
            select(Category).order_by(Category.is_builtin.desc(), Category.name.asc())
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Category | None:
        result = await self.db.execute(select(Category).where(Category.name == name))
        return result.scalar_one_or_none()

    async def create(self, name: str, is_builtin: bool = False) -> Category:
        cat = Category(name=name, is_builtin=is_builtin)
        self.db.add(cat)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise ValueError(f"category already exists: {name}")
        return cat
