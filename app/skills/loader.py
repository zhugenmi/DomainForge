from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.skills.manifest import SkillManifest, SkillManifestError, parse_skill_md


@dataclass
class SkillDescriptor:
    manifest: SkillManifest
    path: Path
    files: list[str]


def load_skill_from_dir(path: Path) -> SkillDescriptor:
    """从目录加载 skill 包：读 SKILL.md 解析 manifest，收集相对文件列表。

    校验：SKILL.md 存在；目录名 == manifest.name。
    """
    skill_md = path / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"SKILL.md 不存在: {skill_md}")

    content = skill_md.read_text(encoding="utf-8")
    try:
        manifest = parse_skill_md(content)
    except SkillManifestError as e:
        raise ValueError(f"SKILL.md manifest 非法: {e}") from e

    if path.name != manifest.name:
        raise ValueError(
            f"目录名与 name 不一致: dir={path.name!r} name={manifest.name!r}"
        )

    files = sorted(
        str(p.relative_to(path))
        for p in path.rglob("*")
        if p.is_file()
    )
    return SkillDescriptor(manifest=manifest, path=path, files=files)
