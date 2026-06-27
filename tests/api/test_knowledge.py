import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.category import Category


@pytest.fixture
def app_with_sqlite_and_categories(monkeypatch):
    """sqlite 内存库 + seed 5 个内置类别。"""
    # 测试隔离：禁用 Redis，preview_store/cache/rate_limit 走进程内退路，
    # 避免 TestClient 每请求新事件循环导致 Redis 单例 "Event loop is closed"。
    from app.configs.settings import settings
    from app.services.redis import reset_redis_for_test

    monkeypatch.setattr(settings, "REDIS_ENABLED", False)
    reset_redis_for_test()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # seed built-in categories
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            for name in ["legal", "finance", "medical", "insurance", "enterprise"]:
                s.add(Category(name=name, is_builtin=True))
            await s.commit()

    asyncio.get_event_loop().run_until_complete(_init())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    from app.main import app
    app.dependency_overrides[
        __import__("app.database.session", fromlist=["get_db"]).get_db
    ] = _get_db

    # mock LLM provider
    class _StubLLM:
        model = "stub"

        async def generate(self, messages, **kwargs):
            return "stubbed answer"

        async def stream(self, messages, **kwargs):
            yield "stubbed"

        async def embed(self, texts, **kwargs):
            # 返回与 EMBEDDING_DIMENSION 一致长度的向量
            return [[0.0] * 1024 for _ in texts]

    import app.llm.providers.openai as openai_mod
    monkeypatch.setattr(openai_mod, "OpenAIProvider", lambda *a, **k: _StubLLM())

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_sqlite_and_categories):
    return TestClient(app_with_sqlite_and_categories)


def test_list_categories_returns_builtins(client):
    r = client.get("/api/v1/knowledge/categories")
    assert r.status_code == 200
    cats = r.json()
    names = [c["name"] for c in cats]
    assert "legal" in names
    assert "finance" in names
    assert "medical" in names
    assert "insurance" in names
    assert "enterprise" in names
    for c in cats:
        assert c["file_count"] == 0
        assert c["word_count"] == 0


def test_create_user_category(client):
    r = client.post("/api/v1/knowledge/categories", json={"name": "HR"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "hr"  # 后端 lower
    assert data["is_builtin"] is False

    # 重复创建 409
    r2 = client.post("/api/v1/knowledge/categories", json={"name": "HR"})
    assert r2.status_code == 409


def test_create_category_empty_name(client):
    r = client.post("/api/v1/knowledge/categories", json={"name": "  "})
    assert r.status_code == 400


def test_upload_preview_txt_file(client):
    content = "第一条 合同的订立需要要约与承诺。\n第二条 当事人应当具有相应的民事权利能力。"
    r = client.post(
        "/api/v1/knowledge/upload",
        data={
            "domain": "legal",
            "chunk_strategy": "legal",
            "chunk_size": "500",
            "chunk_overlap": "50",
        },
        files=[
            ("files", ("民法典摘要.txt", content.encode("utf-8"), "text/plain")),
        ],
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["domain"] == "legal"
    assert data["chunk_strategy"] == "legal"
    assert data["embedding_dimension"] == 1024
    assert len(data["files"]) == 1
    f = data["files"][0]
    assert f["filename"] == "民法典摘要.txt"
    assert f["file_type"] == "txt"
    assert f["char_count"] == len(content)
    assert f["chunk_count"] >= 1
    assert len(f["sample_chunks"]) <= 3
    assert "session_id" in data


def test_upload_rejects_unknown_category(client):
    r = client.post(
        "/api/v1/knowledge/upload",
        data={"domain": "nonexistent", "chunk_strategy": "semantic"},
        files=[("files", ("a.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 404


def test_confirm_import_persists_documents_and_chunks(client):
    # 1. upload
    content = "第一条 内容A。\n第二条 内容B。"
    up = client.post(
        "/api/v1/knowledge/upload",
        data={"domain": "legal", "chunk_strategy": "legal"},
        files=[("files", ("doc.txt", content.encode("utf-8"), "text/plain"))],
    )
    assert up.status_code == 200
    session_id = up.json()["session_id"]

    # 2. confirm
    cf = client.post("/api/v1/knowledge/confirm", json={"session_id": session_id})
    assert cf.status_code == 200, cf.text
    result = cf.json()
    assert len(result["document_ids"]) == 1
    assert result["total_chunks"] >= 1

    # 3. 列出类别统计应反映新增
    cats = client.get("/api/v1/knowledge/categories").json()
    legal = next(c for c in cats if c["name"] == "legal")
    assert legal["file_count"] == 1
    assert legal["word_count"] > 0

    # 4. 列出文档
    docs = client.get("/api/v1/knowledge/categories/legal/documents").json()
    assert len(docs) == 1
    assert docs[0]["title"] == "doc.txt"
    assert docs[0]["file_type"] == "txt"
    assert docs[0]["status"] == "indexed"
    assert docs[0]["chunk_count"] >= 1


def test_confirm_expired_session_returns_410(client):
    r = client.post(
        "/api/v1/knowledge/confirm",
        json={"session_id": str(uuid.uuid4())},
    )
    assert r.status_code == 410


def test_delete_document_cascades_chunks(client):
    # import 一个文档
    up = client.post(
        "/api/v1/knowledge/upload",
        data={"domain": "legal", "chunk_strategy": "legal"},
        files=[("files", ("to_del.txt", "第一条 X。\n第二条 Y。".encode("utf-8"), "text/plain"))],
    )
    sid = up.json()["session_id"]
    cf = client.post("/api/v1/knowledge/confirm", json={"session_id": sid})
    doc_id = cf.json()["document_ids"][0]

    # delete
    r = client.delete(f"/api/v1/knowledge/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] == doc_id

    # 再删一次 404
    r2 = client.delete(f"/api/v1/knowledge/documents/{doc_id}")
    assert r2.status_code == 404

    # 类别统计应回到 0
    cats = client.get("/api/v1/knowledge/categories").json()
    legal = next(c for c in cats if c["name"] == "legal")
    assert legal["file_count"] == 0


def test_legacy_index_endpoint_still_works(client):
    r = client.post(
        "/api/v1/knowledge/index",
        json={"domain": "legal", "title": "legacy", "content": "传统文本导入测试"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "document_id" in data
    assert data["chunks"] >= 1
