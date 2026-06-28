from __future__ import annotations

import re
from dataclasses import dataclass

import frontmatter

_NAME_RE = re.compile(r"^[a-z0-9-]+$")


class SkillManifestError(ValueError):
    """SKILL.md manifest 解析或校验失败。"""


@dataclass
class SkillManifest:
    name: str
    description: str
    version: str
    author: str
    license: str
    body_md: str


def parse_skill_md(content: str) -> SkillManifest:
    """解析 SKILL.md 内容：YAML frontmatter + markdown 正文。

    name 必填且匹配 ^[a-z0-9-]+$；description 必填非空；
    version/author/license 可选，缺省为空串。
    """
    try:
        post = frontmatter.loads(content)
    except Exception as e:
        raise SkillManifestError(f"frontmatter 解析失败: {e}") from e

    name = str(post.get("name", "")).strip()
    description = str(post.get("description", "")).strip()

    if not name:
        raise SkillManifestError("frontmatter 缺少必填字段 name")
    if not _NAME_RE.match(name):
        raise SkillManifestError(
            f"name 非法（须匹配 ^[a-z0-9-]+$）: {name!r}"
        )
    if not description:
        raise SkillManifestError("frontmatter 缺少必填字段 description")

    return SkillManifest(
        name=name,
        description=description,
        version=str(post.get("version", "")).strip(),
        author=str(post.get("author", "")).strip(),
        license=str(post.get("license", "")).strip(),
        body_md=post.content,
    )
