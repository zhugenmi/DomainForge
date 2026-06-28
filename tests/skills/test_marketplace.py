from pathlib import Path

import pytest

from app.skills.marketplace.local_adapter import LocalMarketplaceAdapter


SKILL_A = '''---
name: legal-citation-extractor
description: "Extract legal citations from Chinese legal documents."
version: "1.0.0"
author: example
license: MIT
---

# Legal Citation Extractor

Body for legal.
'''

SKILL_B = '''---
name: finance-report-formatter
description: "Format financial reports into standard structure."
version: "0.9.0"
author: finance-team
license: MIT
---

# Finance Report Formatter

Body for finance.
'''


@pytest.fixture
def marketplace_dir(tmp_path: Path) -> Path:
    root = tmp_path / "marketplace"
    for name, content in [("legal-citation-extractor", SKILL_A),
                          ("finance-report-formatter", SKILL_B)]:
        d = root / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(content, encoding="utf-8")
    return root


@pytest.mark.asyncio
async def test_source_id(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    assert adapter.source_id == "local"


@pytest.mark.asyncio
async def test_search_matches_name(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    results = await adapter.search("legal")
    assert len(results) == 1
    assert results[0].name == "legal-citation-extractor"


@pytest.mark.asyncio
async def test_search_matches_description(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    results = await adapter.search("financial")
    assert len(results) == 1
    assert results[0].name == "finance-report-formatter"


@pytest.mark.asyncio
async def test_search_empty_query_returns_all(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    results = await adapter.search("")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_no_match(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    results = await adapter.search("nonexistent")
    assert results == []


@pytest.mark.asyncio
async def test_info(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    info = await adapter.info("legal-citation-extractor")
    assert info.name == "legal-citation-extractor"
    assert info.version == "1.0.0"
    assert "Body for legal" in info.body_preview


@pytest.mark.asyncio
async def test_info_missing_raises(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    with pytest.raises(KeyError):
        await adapter.info("nope")


@pytest.mark.asyncio
async def test_download_returns_dir_path(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    p = await adapter.download("legal-citation-extractor")
    assert p == marketplace_dir / "legal-citation-extractor"
    assert (p / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_download_missing_raises(marketplace_dir):
    adapter = LocalMarketplaceAdapter(marketplace_dir)
    with pytest.raises(KeyError):
        await adapter.download("nope")


@pytest.mark.asyncio
async def test_empty_marketplace_dir(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir()
    adapter = LocalMarketplaceAdapter(root)
    assert await adapter.search("") == []
