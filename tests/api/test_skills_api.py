from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database.session import async_session_factory
from app.skills.registry import SkillRegistry
from app.skills.marketplace.local_adapter import LocalMarketplaceAdapter
from app.skills.service import SkillService


SKILL_MD = """---
name: legal-citation-extractor
description: "Extract legal citations."
version: "1.0.0"
author: example
license: MIT
---

# Legal Citation Extractor

Body.
"""


@pytest.fixture
def marketplace_dir(tmp_path: Path) -> Path:
    root = tmp_path / "marketplace"
    d = root / "legal-citation-extractor"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    return root


@pytest.fixture
def installed_root(tmp_path: Path) -> Path:
    r = tmp_path / "installed"
    r.mkdir()
    return r


@pytest.fixture
async def client(monkeypatch, marketplace_dir, installed_root, db):
    """Override SkillService dependency with temp dirs + in-memory DB."""
    from app.api import skills as skills_api

    registry = SkillRegistry()
    marketplace = LocalMarketplaceAdapter(marketplace_dir)

    async def _get_service():
        return SkillService(
            db=db,
            registry=registry,
            marketplace=marketplace,
            installed_root=installed_root,
        )

    monkeypatch.setattr(skills_api, "get_skill_service", _get_service)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_search_marketplace(client):
    res = await client.get("/api/v1/skills/marketplace?q=legal")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["name"] == "legal-citation-extractor"


@pytest.mark.asyncio
async def test_get_marketplace_info(client):
    res = await client.get("/api/v1/skills/marketplace/legal-citation-extractor")
    assert res.status_code == 200
    assert res.json()["name"] == "legal-citation-extractor"


@pytest.mark.asyncio
async def test_get_marketplace_info_missing_returns_404(client):
    res = await client.get("/api/v1/skills/marketplace/nope")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_install_then_list_then_detail(client):
    res = await client.post("/api/v1/skills/marketplace/legal-citation-extractor/install")
    assert res.status_code == 200
    assert res.json()["name"] == "legal-citation-extractor"

    res = await client.get("/api/v1/skills/installed")
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = await client.get("/api/v1/skills/installed/legal-citation-extractor")
    assert res.status_code == 200
    assert "# Legal Citation Extractor" in res.json()["body_md"]


@pytest.mark.asyncio
async def test_install_duplicate_returns_409(client):
    await client.post("/api/v1/skills/marketplace/legal-citation-extractor/install")
    res = await client.post("/api/v1/skills/marketplace/legal-citation-extractor/install")
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_set_enabled(client):
    await client.post("/api/v1/skills/marketplace/legal-citation-extractor/install")
    res = await client.patch(
        "/api/v1/skills/installed/legal-citation-extractor",
        json={"enabled": False},
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is False


@pytest.mark.asyncio
async def test_uninstall(client):
    await client.post("/api/v1/skills/marketplace/legal-citation-extractor/install")
    res = await client.delete("/api/v1/skills/installed/legal-citation-extractor")
    assert res.status_code == 204
    res = await client.get("/api/v1/skills/installed")
    assert res.json() == []


@pytest.mark.asyncio
async def test_uninstall_missing_returns_404(client):
    res = await client.delete("/api/v1/skills/installed/nope")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_installed_missing_returns_404(client):
    res = await client.get("/api/v1/skills/installed/nope")
    assert res.status_code == 404
