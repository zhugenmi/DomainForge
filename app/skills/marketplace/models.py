from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SkillPackageInfo:
    skill_id: str
    name: str
    description: str
    version: str
    author: str
    license: str
    source: str
    body_preview: str
