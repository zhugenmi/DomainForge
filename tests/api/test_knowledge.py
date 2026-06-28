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

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_init())
    loop.close()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    from app.main import app
    app.dependency_overrides[
        __import__("app.database.session", fromlist=["get_db"]).get_db
    ] = _get_db

    # 后台导入任务使用独立 session factory（不走 get_db 依赖注入），
    # 这里把 knowledge 模块引用的 factory 指向测试 sqlite factory
    import app.api.knowledge as knowledge_mod
    monkeypatch.setattr(knowledge_mod, "async_session_factory", factory)

    # 清空 import job store，避免跨测试残留
    from app.services.import_job_store import import_job_store
    import_job_store._jobs.clear()

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
    import app.api.knowledge as knowledge_mod
    monkeypatch.setattr(openai_mod, "OpenAIProvider", lambda *a, **k: _StubLLM())
    # confirm_import / _run_import 通过 knowledge 模块内的名字引用 OpenAIProvider，
    # 必须同步 patch 该绑定，否则后台任务会用真实 provider 打外部 API。
    monkeypatch.setattr(knowledge_mod, "OpenAIProvider", lambda *a, **k: _StubLLM())

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


async def _wait_for_job(app, job_id: str, timeout: float = 5.0) -> dict:
    """异步轮询导入 job。与后台任务共享事件循环，asyncio.sleep 让出控制权使其推进。"""
    import asyncio
    import time

    import httpx

    deadline = time.time() + timeout
    last = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        while time.time() < deadline:
            r = await ac.get(f"/api/v1/knowledge/import/{job_id}/status")
            assert r.status_code == 200, r.text
            last = r.json()
            if last["status"] in ("succeeded", "failed"):
                return last
            await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish, last status: {last}")


async def test_confirm_import_persists_documents_and_chunks(app_with_sqlite_and_categories):
    app = app_with_sqlite_and_categories
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. upload
        content = "第一条 内容A。\n第二条 内容B。"
        up = await ac.post(
            "/api/v1/knowledge/upload",
            data={"domain": "legal", "chunk_strategy": "legal"},
            files=[("files", ("doc.txt", content.encode("utf-8"), "text/plain"))],
        )
        assert up.status_code == 200
        session_id = up.json()["session_id"]

        # 2. confirm 立即返回 202 + job_id
        cf = await ac.post("/api/v1/knowledge/confirm", json={"session_id": session_id})
        assert cf.status_code == 202, cf.text
        job_id = cf.json()["job_id"]

    # 3. 轮询直到完成（独立 client，确保后台任务在循环上推进）
    result = await _wait_for_job(app, job_id)
    assert result["status"] == "succeeded", result
    assert len(result["document_ids"]) == 1
    assert result["total_chunks"] >= 1
    assert result["processed_chunks"] == result["total_chunks"]

    # 4. 列出类别统计应反映新增
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        cats = (await ac.get("/api/v1/knowledge/categories")).json()
        legal = next(c for c in cats if c["name"] == "legal")
        assert legal["file_count"] == 1
        assert legal["word_count"] > 0

        docs = (await ac.get("/api/v1/knowledge/categories/legal/documents")).json()
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


async def test_confirm_import_marks_failed_on_embed_error(app_with_sqlite_and_categories, monkeypatch):
    """embed 抛错时 job 应转 failed，文档标 failed，不卡 parsing。"""
    app = app_with_sqlite_and_categories
    import httpx

    # 让 _run_import 内的 OpenAIProvider 返回一个 embed 必失败的 stub
    class _BoomLLM:
        model = "boom"

        async def generate(self, messages, **kwargs):
            return ""

        async def stream(self, messages, **kwargs):
            yield ""

        async def embed(self, texts, **kwargs):
            raise RuntimeError("embed boom")

    import app.api.knowledge as knowledge_mod
    monkeypatch.setattr(knowledge_mod, "OpenAIProvider", lambda *a, **k: _BoomLLM())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        up = await ac.post(
            "/api/v1/knowledge/upload",
            data={"domain": "legal", "chunk_strategy": "legal"},
            files=[("files", ("boom.txt", "第一条 A。".encode("utf-8"), "text/plain"))],
        )
        sid = up.json()["session_id"]
        cf = await ac.post("/api/v1/knowledge/confirm", json={"session_id": sid})
        assert cf.status_code == 202

    result = await _wait_for_job(app, cf.json()["job_id"])
    assert result["status"] == "failed"
    assert "embed boom" in (result["error"] or "")

    # 失败回滚 → 无孤儿文档
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        docs = (await ac.get("/api/v1/knowledge/categories/legal/documents")).json()
        assert docs == []


async def test_legal_import_persists_chapter_and_article_metadata(app_with_sqlite_and_categories):
    """legal 导入后 chunk metadata 应带 article + chapter（regression: 上传曾丢弃 chunk.metadata）。"""
    app = app_with_sqlite_and_categories
    import httpx
    from sqlalchemy import select
    from app.database.models.chunk import DocumentChunk
    from app.database.session import get_db as _get_db  # noqa: F401

    transport = httpx.ASGITransport(app=app)
    content = (
        "第一章　总则\n"
        "第一条　立法目的。\n内容A。\n"
        "第二条　适用范围。\n内容B。\n"
        "第三章　处罚\n"
        "第三十条　处罚条款。\n"
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        up = await ac.post(
            "/api/v1/knowledge/upload",
            data={"domain": "legal", "chunk_strategy": "legal"},
            files=[("files", ("law.txt", content.encode("utf-8"), "text/plain"))],
        )
        assert up.status_code == 200, up.text
        sid = up.json()["session_id"]
        cf = await ac.post("/api/v1/knowledge/confirm", json={"session_id": sid})
        assert cf.status_code == 202
    result = await _wait_for_job(app, cf.json()["job_id"])
    assert result["status"] == "succeeded"
    doc_id = result["document_ids"][0]

    import app.api.knowledge as knowledge_mod
    factory = knowledge_mod.async_session_factory
    async with factory() as s:
        chunks = (await s.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(doc_id))
            .order_by(DocumentChunk.created_at)
        )).scalars().all()
        assert len(chunks) >= 3
        first = chunks[0].metadata_
        assert first.get("article") == "第一条"
        assert first.get("chapter") == "第一章　总则"
        last = chunks[-1].metadata_
        assert last.get("article") == "第三十条"
        assert last.get("chapter") == "第三章　处罚"


async def test_delete_document_cascades_chunks(app_with_sqlite_and_categories):
    app = app_with_sqlite_and_categories
    import httpx

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        up = await ac.post(
            "/api/v1/knowledge/upload",
            data={"domain": "legal", "chunk_strategy": "legal"},
            files=[("files", ("to_del.txt", "第一条 X。\n第二条 Y。".encode("utf-8"), "text/plain"))],
        )
        sid = up.json()["session_id"]
        cf = await ac.post("/api/v1/knowledge/confirm", json={"session_id": sid})
        assert cf.status_code == 202
    result = await _wait_for_job(app, cf.json()["job_id"])
    assert result["status"] == "succeeded"
    doc_id = result["document_ids"][0]

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        # delete
        r = await ac.delete(f"/api/v1/knowledge/documents/{doc_id}")
        assert r.status_code == 200
        assert r.json()["deleted"] == doc_id

        # 再删一次 404
        r2 = await ac.delete(f"/api/v1/knowledge/documents/{doc_id}")
        assert r2.status_code == 404

        # 类别统计应回到 0
        cats = (await ac.get("/api/v1/knowledge/categories")).json()
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
