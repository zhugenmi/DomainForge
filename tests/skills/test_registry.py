from pathlib import Path

from app.skills.loader import SkillDescriptor
from app.skills.manifest import SkillManifest
from app.skills.registry import SkillRegistry


def _desc(name: str) -> SkillDescriptor:
    return SkillDescriptor(
        manifest=SkillManifest(
            name=name, description="d", version="", author="", license="", body_md="b"
        ),
        path=Path(f"/tmp/{name}"),
        files=["SKILL.md"],
    )


def test_add_and_get():
    reg = SkillRegistry()
    d = _desc("foo")
    reg.add(d)
    assert reg.get("foo") is d


def test_remove():
    reg = SkillRegistry()
    reg.add(_desc("foo"))
    reg.remove("foo")
    assert reg.get("foo") is None


def test_list_all():
    reg = SkillRegistry()
    reg.add(_desc("foo"))
    reg.add(_desc("bar"))
    names = sorted(d.manifest.name for d in reg.list_all())
    assert names == ["bar", "foo"]


def test_add_overwrite():
    reg = SkillRegistry()
    reg.add(_desc("foo"))
    d2 = _desc("foo")
    reg.add(d2)
    assert reg.get("foo") is d2
    assert len(reg.list_all()) == 1


def test_remove_missing_is_noop():
    reg = SkillRegistry()
    reg.remove("nope")  # 不抛


def test_get_missing_returns_none():
    reg = SkillRegistry()
    assert reg.get("nope") is None
