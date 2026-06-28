import pytest

from app.database.models.installed_skill import InstalledSkill
from app.database.repositories.skill_repo import SkillRepo


@pytest.mark.asyncio
async def test_upsert_and_get(db):
    repo = SkillRepo(db)
    await repo.upsert(
        name="foo",
        version="1.0.0",
        source="local",
        manifest_json='{"name":"foo"}',
        installed_path="/skills/installed/foo",
        enabled=True,
    )
    await db.commit()
    row = await repo.get("foo")
    assert row is not None
    assert row.version == "1.0.0"
    assert row.enabled is True


@pytest.mark.asyncio
async def test_list_all(db):
    repo = SkillRepo(db)
    await repo.upsert(name="foo", version="", source="local",
                      manifest_json="{}", installed_path="/p/foo", enabled=True)
    await repo.upsert(name="bar", version="", source="local",
                      manifest_json="{}", installed_path="/p/bar", enabled=False)
    await db.commit()
    rows = await repo.list_all()
    names = sorted(r.name for r in rows)
    assert names == ["bar", "foo"]


@pytest.mark.asyncio
async def test_list_enabled(db):
    repo = SkillRepo(db)
    await repo.upsert(name="foo", version="", source="local",
                      manifest_json="{}", installed_path="/p/foo", enabled=True)
    await repo.upsert(name="bar", version="", source="local",
                      manifest_json="{}", installed_path="/p/bar", enabled=False)
    await db.commit()
    rows = await repo.list_enabled()
    assert [r.name for r in rows] == ["foo"]


@pytest.mark.asyncio
async def test_set_enabled(db):
    repo = SkillRepo(db)
    await repo.upsert(name="foo", version="", source="local",
                      manifest_json="{}", installed_path="/p/foo", enabled=True)
    await db.commit()
    await repo.set_enabled("foo", False)
    await db.commit()
    row = await repo.get("foo")
    assert row.enabled is False


@pytest.mark.asyncio
async def test_delete(db):
    repo = SkillRepo(db)
    await repo.upsert(name="foo", version="", source="local",
                      manifest_json="{}", installed_path="/p/foo", enabled=True)
    await db.commit()
    await repo.delete("foo")
    await db.commit()
    assert await repo.get("foo") is None
