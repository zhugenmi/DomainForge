from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.loader import load_skill_from_dir
from app.skills.manifest import SkillManifest
from app.skills.marketplace.base import MarketplaceAdapter
from app.skills.marketplace.models import SkillPackageInfo
from app.skills.registry import SkillRegistry
from app.database.repositories.skill_repo import SkillRepo


@dataclass
class InstalledSkillDTO:
    name: str
    description: str
    version: str
    author: str
    license: str
    source: str
    enabled: bool
    installed_at: str


@dataclass
class InstalledSkillDetailDTO:
    name: str
    description: str
    version: str
    author: str
    license: str
    source: str
    enabled: bool
    installed_at: str
    body_md: str
    files: list[str]


def _manifest_json(m: SkillManifest) -> str:
    return json.dumps(asdict(m), ensure_ascii=False)


def _dto_from_row(row, manifest: SkillManifest | None = None) -> InstalledSkillDTO:
    if manifest is None:
        try:
            data = json.loads(row.manifest_json)
        except json.JSONDecodeError:
            data = {}
    else:
        data = asdict(manifest)
    return InstalledSkillDTO(
        name=row.name,
        description=data.get("description", ""),
        version=data.get("version", row.version),
        author=data.get("author", ""),
        license=data.get("license", ""),
        source=row.source,
        enabled=row.enabled,
        installed_at=row.installed_at.isoformat() if row.installed_at else "",
    )


class SkillService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        registry: SkillRegistry,
        marketplace: MarketplaceAdapter,
        installed_root: Path,
    ):
        self.db = db
        self.registry = registry
        self.marketplace = marketplace
        self.installed_root = installed_root
        self._repo = SkillRepo(db)

    async def search_marketplace(self, query: str) -> list[SkillPackageInfo]:
        return await self.marketplace.search(query)

    async def get_marketplace_info(self, skill_id: str) -> SkillPackageInfo:
        return await self.marketplace.info(skill_id)

    async def list_installed(self) -> list[InstalledSkillDTO]:
        rows = await self._repo.list_all()
        return [_dto_from_row(r) for r in rows]

    async def get_installed(self, name: str) -> InstalledSkillDetailDTO:
        row = await self._repo.get(name)
        if row is None:
            raise KeyError(name)
        desc = load_skill_from_dir(Path(row.installed_path))
        dto = _dto_from_row(row, desc.manifest)
        return InstalledSkillDetailDTO(
            **{f.name: getattr(dto, f.name) for f in fields(dto)},
            body_md=desc.manifest.body_md,
            files=desc.files,
        )

    async def install(self, skill_id: str) -> InstalledSkillDTO:
        existing = await self._repo.get(skill_id)
        if existing is not None:
            raise ValueError(f"skill 已安装: {skill_id}")

        src = await self.marketplace.download(skill_id)
        desc = load_skill_from_dir(src)
        if desc.manifest.name != skill_id:
            raise ValueError(
                f"skill_id 与 manifest.name 不一致: {skill_id} vs {desc.manifest.name}"
            )

        dest = self.installed_root / desc.manifest.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

        installed_path = str(dest)
        await self._repo.upsert(
            name=desc.manifest.name,
            version=desc.manifest.version,
            source=self.marketplace.source_id,
            manifest_json=_manifest_json(desc.manifest),
            installed_path=installed_path,
            enabled=True,
        )
        await self.db.commit()

        desc_installed = load_skill_from_dir(dest)
        self.registry.add(desc_installed)

        row = await self._repo.get(desc.manifest.name)
        return _dto_from_row(row, desc_installed.manifest)

    async def uninstall(self, name: str) -> None:
        row = await self._repo.get(name)
        if row is None:
            raise KeyError(name)

        target = Path(row.installed_path).resolve()
        root = self.installed_root.resolve()
        try:
            target.relative_to(root)
        except ValueError as e:
            raise ValueError(f"卸载路径不在 installed_root 之内: {target}") from e

        self.registry.remove(name)
        if target.is_dir():
            shutil.rmtree(target)
        await self._repo.delete(name)
        await self.db.commit()

    async def set_enabled(self, name: str, enabled: bool) -> None:
        row = await self._repo.get(name)
        if row is None:
            raise KeyError(name)
        await self._repo.set_enabled(name, enabled)
        await self.db.commit()
        if enabled:
            desc = load_skill_from_dir(Path(row.installed_path))
            self.registry.add(desc)
        else:
            self.registry.remove(name)
