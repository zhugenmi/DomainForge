import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.category import Category


@pytest.fixture
def client(monkeypatch):
    from app.configs.settings import settings
    from app.services.redis import reset_redis_for_test

    monkeypatch.setattr(settings, "REDIS_ENABLED", False)
    reset_redis_for_test()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            s.add(Category(name="legal", is_builtin=True))
            await s.commit()

    asyncio.run(_init())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    from app.main import app
    app.dependency_overrides[
        __import__("app.database.session", fromlist=["get_db"]).get_db
    ] = _get_db

    class _StubLLM:
        model = "stub"

        async def generate(self, messages, **kwargs):
            return "stubbed answer"

        async def stream(self, messages, **kwargs):
            yield "stubbed"

        async def embed(self, texts, **kwargs):
            return [[0.0] * 1024 for _ in texts]

        async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
            return None

    import app.llm.providers.openai as openai_mod
    import app.llm.router.model_router as router_mod

    _stub_factory = lambda *a, **k: _StubLLM()
    monkeypatch.setattr(openai_mod, "OpenAIProvider", _stub_factory)
    monkeypatch.setitem(router_mod._PROVIDERS, "openai", _stub_factory)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_chat_uploads_txt(client):
    content = b"hello world"
    files = [("files", ("a.txt", content, "text/plain"))]
    resp = client.post("/api/v1/chat/uploads", files=files)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["attachment_ids"]) == 1
    assert data["previews"][0]["filename"] == "a.txt"
    assert data["previews"][0]["chars"] == 11


def test_chat_uploads_rejects_too_many(client, monkeypatch):
    from app.configs import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "MAX_CHAT_ATTACHMENTS", 1)
    files = [
        ("files", ("a.txt", b"x", "text/plain")),
        ("files", ("b.txt", b"y", "text/plain")),
    ]
    resp = client.post("/api/v1/chat/uploads", files=files)
    assert resp.status_code == 400


def test_chat_uploads_rejects_oversize(client, monkeypatch):
    from app.configs import settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "MAX_CHAT_ATTACHMENT_MB", 0)
    files = [("files", ("big.txt", b"x" * 100, "text/plain"))]
    resp = client.post("/api/v1/chat/uploads", files=files)
    assert resp.status_code == 400


def test_chat_post_stream_returns_sse(client, monkeypatch):
    """POST /chat/stream 应返回 SSE 流，含 final_answer 事件。"""
    captured = {}

    class _StubRuntime:
        async def run_stream(self, state):
            captured["state"] = state
            state.final_answer = "stubbed answer"
            yield 'data: {"event":"final_answer","data":{"answer":"stubbed answer"}}\n\n'

    async def _fake_build_runtime(db, session_id, user_id=None, agent=None, override_model=None):
        return _StubRuntime()

    from app.api import chat as chat_mod
    monkeypatch.setattr(chat_mod, "_build_runtime", _fake_build_runtime)

    resp = client.post(
        "/api/v1/chat/stream",
        json={"query": "hi", "web_search": True, "deep_think": True},
    )
    assert resp.status_code == 200, resp.text
    assert "final_answer" in resp.text
    assert "stubbed answer" in resp.text
    # state 收到开关
    assert captured["state"].web_search is True
    assert captured["state"].deep_think is True


def test_chat_post_stream_pops_attachments(client, monkeypatch):
    """attachment_ids 应被 pop 为 state.attachments，且 store 中删除。"""
    from app.services.attachment_store import attachment_store

    aid = asyncio.run(
        attachment_store.put("a.txt", "ATTACH BODY")
    )

    captured = {}

    class _StubRuntime:
        async def run_stream(self, state):
            captured["state"] = state
            state.final_answer = "ok"
            yield 'data: {"event":"final_answer","data":{"answer":"ok"}}\n\n'

    async def _fake_build_runtime(db, session_id, user_id=None, agent=None, override_model=None):
        return _StubRuntime()

    from app.api import chat as chat_mod
    monkeypatch.setattr(chat_mod, "_build_runtime", _fake_build_runtime)

    resp = client.post(
        "/api/v1/chat/stream",
        json={"query": "hi", "attachment_ids": [str(aid)]},
    )
    assert resp.status_code == 200, resp.text
    assert captured["state"].attachments[0]["content"] == "ATTACH BODY"
    # 调用后 store 中应已删除
    got = asyncio.run(attachment_store.get(aid))
    assert got is None


def test_get_chat_stream_has_deprecation_header(client, monkeypatch):
    class _StubRuntime:
        async def run_stream(self, state):
            state.final_answer = "ok"
            yield 'data: {"event":"final_answer","data":{"answer":"ok"}}\n\n'

    async def _fake_build_runtime(db, session_id, user_id=None, agent=None, override_model=None):
        return _StubRuntime()

    from app.api import chat as chat_mod
    monkeypatch.setattr(chat_mod, "_build_runtime", _fake_build_runtime)

    resp = client.get("/api/v1/chat/stream", params={"query": "hi"})
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"


def test_chat_post_with_attachments_and_flags(client, monkeypatch):
    """POST /chat（非流式）也应处理新字段。"""
    from app.services.attachment_store import attachment_store

    aid = asyncio.run(
        attachment_store.put("note.txt", "NOTE TEXT")
    )

    captured = {}

    class _StubRuntime:
        async def run(self, state):
            captured["state"] = state
            state.intent = "chat"
            state.final_answer = "ans"
            return state

    async def _fake_build_runtime(db, session_id, user_id=None, agent=None, override_model=None):
        return _StubRuntime()

    from app.api import chat as chat_mod
    monkeypatch.setattr(chat_mod, "_build_runtime", _fake_build_runtime)

    resp = client.post(
        "/api/v1/chat",
        json={
            "query": "hi",
            "web_search": True,
            "deep_think": True,
            "attachment_ids": [str(aid)],
        },
    )
    assert resp.status_code == 200, resp.text
    assert captured["state"].web_search is True
    assert captured["state"].deep_think is True
    assert captured["state"].attachments[0]["content"] == "NOTE TEXT"
