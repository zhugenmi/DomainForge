from __future__ import annotations

from app.skills.registry import SkillRegistry

_HEADER = (
    "以下是你可以使用的技能指令。当任务相关时，严格遵循对应技能的指令行事。"
)


def build_skill_context_block(registry: SkillRegistry) -> str:
    """组装所有 enabled skill 的正文为系统提示上下文块。

    无 skill 时返回空串（调用方据此决定是否拼接）。
    """
    descs = registry.list_all()
    if not descs:
        return ""

    parts = [_HEADER]
    for d in descs:
        parts.append(f"## 技能：{d.manifest.name}\n{d.manifest.body_md}")
    return "\n\n".join(parts)
