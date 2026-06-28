from pathlib import Path

import pytest

from app.database.repositories.skill_repo import SkillRepo
from app.skills.registry import skill_registry


SKILL_MD = """---
name: foo
description: "x"
---

# Foo

body
"""


def _make_factory(db):
    class _F:
        async def __aenter__(self):
            return db
        async def __aexit__(self, *a):
            pass
    return _F


@pytest.mark.asyncio
async def test_lifespan_loads_enabled_skills(db, monkeypatch, tmp_path):
    # 安装一个 skill 到临时 installed_root，enabled=True
    installed = tmp_path / "installed" / "foo"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    repo = SkillRepo(db)
    await repo.upsert(
        name="foo", version="", source="local",
        manifest_json="{}", installed_path=str(installed), enabled=True,
    )
    await db.commit()

    skill_registry.remove("foo")  # 清场
    monkeypatch.setattr(
        "app.main.async_session_factory",
        _make_factory(db),
    )
    from app.main import _load_installed_skills
    await _load_installed_skills()
    assert skill_registry.get("foo") is not None
    skill_registry.remove("foo")
