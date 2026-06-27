import pytest

from app.database.models.category import Category
from app.database.models.document import Document
from app.tools.builtin.knowledge_catalog_tool import ListKnowledgeBasesTool


@pytest.mark.asyncio
async def test_catalog_returns_categories_with_stats(db):
    db.add(Category(name="product", is_builtin=True))
    db.add(Category(name="faq", is_builtin=False))
    db.add(
        Document(
            domain="product",
            title="P1",
            word_count=100,
        )
    )
    db.add(
        Document(
            domain="product",
            title="P2",
            word_count=50,
        )
    )
    db.add(Document(domain="faq", title="Q1", word_count=20))
    await db.flush()

    tool = ListKnowledgeBasesTool(db=db)
    catalog = await tool.execute()

    by_name = {c["name"]: c for c in catalog}
    assert by_name["product"]["is_builtin"] is True
    assert by_name["product"]["file_count"] == 2
    assert by_name["product"]["word_count"] == 150
    assert by_name["faq"]["file_count"] == 1
    assert by_name["faq"]["word_count"] == 20


@pytest.mark.asyncio
async def test_catalog_empty_when_no_categories(db):
    tool = ListKnowledgeBasesTool(db=db)
    catalog = await tool.execute()
    assert catalog == []


@pytest.mark.asyncio
async def test_catalog_category_without_documents(db):
    db.add(Category(name="empty", is_builtin=False))
    await db.flush()

    tool = ListKnowledgeBasesTool(db=db)
    catalog = await tool.execute()
    assert len(catalog) == 1
    assert catalog[0]["name"] == "empty"
    assert catalog[0]["file_count"] == 0
    assert catalog[0]["word_count"] == 0
