from __future__ import annotations

from pathlib import Path

from app.skills.manifest import SkillManifestError, parse_skill_md
from app.skills.marketplace.base import MarketplaceAdapter
from app.skills.marketplace.models import SkillPackageInfo

_PREVIEW_LEN = 300


class LocalMarketplaceAdapter(MarketplaceAdapter):
    """读本地 skills/marketplace/ 目录的 mock marketplace。

    skill_id == 目录名 == manifest.name。download 返回包目录 Path
    （由 SkillService 负责拷贝到 installed/）。
    """

    def __init__(self, root: Path):
        self._root = root

    @property
    def source_id(self) -> str:
        return "local"

    def _list_skill_dirs(self) -> list[Path]:
        if not self._root.is_dir():
            return []
        return sorted(
            p for p in self._root.iterdir()
            if p.is_dir() and (p / "SKILL.md").is_file()
        )

    def _load(self, skill_dir: Path) -> SkillPackageInfo:
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        try:
            m = parse_skill_md(content)
        except SkillManifestError as e:
            raise ValueError(f"marketplace skill {skill_dir.name!r} manifest 非法: {e}") from e
        return SkillPackageInfo(
            skill_id=skill_dir.name,
            name=m.name,
            description=m.description,
            version=m.version,
            author=m.author,
            license=m.license,
            source=self.source_id,
            body_preview=m.body_md[:_PREVIEW_LEN],
        )

    async def search(self, query: str) -> list[SkillPackageInfo]:
        q = query.strip().lower()
        results = []
        for d in self._list_skill_dirs():
            info = self._load(d)
            if not q or q in info.name.lower() or q in info.description.lower():
                results.append(info)
        return results

    async def info(self, skill_id: str) -> SkillPackageInfo:
        d = self._root / skill_id
        if not d.is_dir() or not (d / "SKILL.md").is_file():
            raise KeyError(skill_id)
        return self._load(d)

    async def download(self, skill_id: str) -> Path:
        d = self._root / skill_id
        if not d.is_dir() or not (d / "SKILL.md").is_file():
            raise KeyError(skill_id)
        return d
