import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.agent import Agent
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
            s.add(
                Agent(
                    name="法律咨询",
                    model_name="gpt-4o-mini",
                    domain="legal",
                    is_builtin=True,
                    system_prompt="你是法律助手",
                )
            )
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

    captured = {"system": ""}

    class _StubLLM:
        model = "stub"

        async def generate(self, messages, **kwargs):
            import sys
            print(f"GENERATE: {messages[0]['content'][:80]}", file=sys.stderr)
            captured["system"] = messages[0]["content"]
            return "stubbed answer"

        async def stream(self, messages, **kwargs):
            captured["system"] = messages[0]["content"]
            yield "stubbed"

        async def embed(self, texts, **kwargs):
            return [[0.0] * 1024 for _ in texts]

        async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
            return None

    import app.llm.providers.openai as openai_mod
    import app.llm.router.model_router as router_mod

    _stub_factory = lambda *a, **k: _StubLLM()
    monkeypatch.setattr(openai_mod, "OpenAIProvider", _stub_factory)
    # ModelRouter._PROVIDERS 持有 import 时的类引用，必须同步替换才能让 get_provider() 命中 stub
    monkeypatch.setitem(router_mod._PROVIDERS, "openai", _stub_factory)

    app.state._test_captured = captured  # type: ignore[attr-defined]

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_chat_with_agent_id_injects_system_prompt(client):
    agent_id = client.get("/api/v1/agents").json()[0]["id"]
    resp = client.post(
        "/api/v1/chat",
        json={"query": "你好", "agent_id": agent_id},
    )
    assert resp.status_code == 200, resp.text
    captured = client.app.state._test_captured  # type: ignore[attr-defined]
    assert "你是法律助手" in captured["system"]


def test_chat_with_nonexistent_agent_returns_404(client):
    resp = client.post(
        "/api/v1/chat",
        json={"query": "你好", "agent_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
