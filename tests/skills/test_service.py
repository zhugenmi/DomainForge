import json
from pathlib import Path

import pytest

from app.database.repositories.skill_repo import SkillRepo
from app.skills.loader import SkillDescriptor
from app.skills.marketplace.local_adapter import LocalMarketplaceAdapter
from app.skills.registry import SkillRegistry
from app.skills.service import SkillService


SKILL_MD = '''---
name: legal-citation-extractor
description: "Extract legal citations."
version: "1.0.0"
author: example
license: MIT
---

# Legal Citation Extractor

Body.
'''


@pytest.fixture
def installed_root(tmp_path: Path) -> Path:
    return tmp_path / "installed"


@pytest.fixture
def marketplace_dir(tmp_path: Path) -> Path:
    root = tmp_path / "marketplace"
    d = root / "legal-citation-extractor"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    return root


@pytest.fixture
def service(db, marketplace_dir, installed_root):
    installed_root.mkdir()
    return SkillService(
        db=db,
        registry=SkillRegistry(),
        marketplace=LocalMarketplaceAdapter(marketplace_dir),
        installed_root=installed_root,
    )


@pytest.mark.asyncio
async def test_search_marketplace(service):
    results = await service.search_marketplace("legal")
    assert len(results) == 1
    assert results[0].name == "legal-citation-extractor"


@pytest.mark.asyncio
async def test_install_creates_dir_db_and_registry(service, installed_root):
    dto = await service.install("legal-citation-extractor")
    assert dto.name == "legal-citation-extractor"
    assert (installed_root / "legal-citation-extractor" / "SKILL.md").is_file()
    assert service.registry.get("legal-citation-extractor") is not None
    repo = SkillRepo(service.db)
    row = await repo.get("legal-citation-extractor")
    assert row is not None
    assert row.enabled is True


@pytest.mark.asyncio
async def test_install_duplicate_raises_conflict(service):
    await service.install("legal-citation-extractor")
    with pytest.raises(ValueError, match="已安装"):
        await service.install("legal-citation-extractor")


@pytest.mark.asyncio
async def test_uninstall_removes_dir_db_and_registry(service, installed_root):
    await service.install("legal-citation-extractor")
    await service.uninstall("legal-citation-extractor")
    assert not (installed_root / "legal-citation-extractor").exists()
    assert service.registry.get("legal-citation-extractor") is None
    repo = SkillRepo(service.db)
    assert await repo.get("legal-citation-extractor") is None


@pytest.mark.asyncio
async def test_uninstall_missing_raises(service):
    with pytest.raises(KeyError):
        await service.uninstall("nope")


@pytest.mark.asyncio
async def test_set_enabled_false_removes_from_registry(service):
    await service.install("legal-citation-extractor")
    await service.set_enabled("legal-citation-extractor", False)
    assert service.registry.get("legal-citation-extractor") is None
    repo = SkillRepo(service.db)
    row = await repo.get("legal-citation-extractor")
    assert row.enabled is False


@pytest.mark.asyncio
async def test_set_enabled_true_reloads_to_registry(service):
    await service.install("legal-citation-extractor")
    await service.set_enabled("legal-citation-extractor", False)
    await service.set_enabled("legal-citation-extractor", True)
    assert service.registry.get("legal-citation-extractor") is not None


@pytest.mark.asyncio
async def test_list_installed(service):
    await service.install("legal-citation-extractor")
    rows = await service.list_installed()
    assert len(rows) == 1
    assert rows[0].name == "legal-citation-extractor"
    assert rows[0].enabled is True


@pytest.mark.asyncio
async def test_get_installed_detail(service):
    await service.install("legal-citation-extractor")
    detail = await service.get_installed("legal-citation-extractor")
    assert detail.name == "legal-citation-extractor"
    assert "# Legal Citation Extractor" in detail.body_md
    assert "SKILL.md" in detail.files


@pytest.mark.asyncio
async def test_get_installed_missing_raises(service):
    with pytest.raises(KeyError):
        await service.get_installed("nope")


@pytest.mark.asyncio
async def test_uninstall_rejects_path_traversal(service, installed_root, monkeypatch):
    """uninstall 必须拒绝 installed_root 之外的路径。"""
    await service.install("legal-citation-extractor")
    repo = SkillRepo(service.db)
    row = await repo.get("legal-citation-extractor")
    row.installed_path = str(installed_root.parent / "marketplace" / "legal-citation-extractor")
    await service.db.flush()
    with pytest.raises(ValueError, match="路径"):
        await service.uninstall("legal-citation-extractor")
