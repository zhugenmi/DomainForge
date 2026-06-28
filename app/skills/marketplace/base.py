from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.skills.marketplace.models import SkillPackageInfo


class MarketplaceAdapter(ABC):
    """Skill 市场适配器抽象。后续 ClawhubAdapter 等实现此接口。"""

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    async def search(self, query: str) -> list[SkillPackageInfo]: ...

    @abstractmethod
    async def info(self, skill_id: str) -> SkillPackageInfo: ...

    @abstractmethod
    async def download(self, skill_id: str) -> Path: ...
