from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.installed_skill import InstalledSkill


class SkillRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(
        self,
        *,
        name: str,
        version: str,
        source: str,
        manifest_json: str,
        installed_path: str,
        enabled: bool,
    ) -> InstalledSkill:
        existing = await self.get(name)
        if existing is None:
            row = InstalledSkill(
                name=name,
                version=version,
                source=source,
                manifest_json=manifest_json,
                installed_path=installed_path,
                enabled=enabled,
            )
            self.db.add(row)
            await self.db.flush()
            return row
        existing.version = version
        existing.source = source
        existing.manifest_json = manifest_json
        existing.installed_path = installed_path
        existing.enabled = enabled
        await self.db.flush()
        return existing

    async def get(self, name: str) -> InstalledSkill | None:
        result = await self.db.execute(
            select(InstalledSkill).where(InstalledSkill.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[InstalledSkill]:
        result = await self.db.execute(
            select(InstalledSkill).order_by(InstalledSkill.name.asc())
        )
        return list(result.scalars().all())

    async def list_enabled(self) -> list[InstalledSkill]:
        result = await self.db.execute(
            select(InstalledSkill)
            .where(InstalledSkill.enabled.is_(True))
            .order_by(InstalledSkill.name.asc())
        )
        return list(result.scalars().all())

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self.db.execute(
            update(InstalledSkill)
            .where(InstalledSkill.name == name)
            .values(enabled=enabled)
        )
        await self.db.flush()

    async def delete(self, name: str) -> None:
        await self.db.execute(
            delete(InstalledSkill).where(InstalledSkill.name == name)
        )
        await self.db.flush()
