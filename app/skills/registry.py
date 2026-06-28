from __future__ import annotations

from app.skills.loader import SkillDescriptor


class SkillRegistry:
    """已加载（enabled）skill 的内存镜像。"""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDescriptor] = {}

    def add(self, desc: SkillDescriptor) -> None:
        self._skills[desc.manifest.name] = desc

    def remove(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> SkillDescriptor | None:
        return self._skills.get(name)

    def list_all(self) -> list[SkillDescriptor]:
        return list(self._skills.values())


skill_registry = SkillRegistry()
