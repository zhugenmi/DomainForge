from pathlib import Path

from app.skills.injection import build_skill_context_block
from app.skills.loader import SkillDescriptor
from app.skills.manifest import SkillManifest
from app.skills.registry import SkillRegistry


def _desc(name: str, body: str) -> SkillDescriptor:
    return SkillDescriptor(
        manifest=SkillManifest(
            name=name, description="d", version="", author="", license="", body_md=body
        ),
        path=Path(f"/tmp/{name}"),
        files=["SKILL.md"],
    )


def test_empty_registry_returns_empty_string():
    assert build_skill_context_block(SkillRegistry()) == ""


def test_single_skill_injected():
    reg = SkillRegistry()
    reg.add(_desc("foo", "Do foo things."))
    block = build_skill_context_block(reg)
    assert "技能：foo" in block
    assert "Do foo things." in block
    assert "你可以使用的技能指令" in block


def test_multiple_skills_each_in_own_section():
    reg = SkillRegistry()
    reg.add(_desc("foo", "Foo body."))
    reg.add(_desc("bar", "Bar body."))
    block = build_skill_context_block(reg)
    assert block.count("## 技能：") == 2
    assert "Foo body." in block
    assert "Bar body." in block
