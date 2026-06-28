import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_sqlite(monkeypatch):
    """用 sqlite 内存库替换 get_db，避免依赖真实 Postgres。"""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database.base import Base
    import app.database.models  # noqa: F401  确保所有 model 注册

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    from app.main import app
    app.dependency_overrides[__import__("app.database.session", fromlist=["get_db"]).get_db] = _get_db

    # mock LLM provider
    class _StubLLM:
        model = "stub"

        async def generate(self, messages, **kwargs):
            return "stubbed answer"

        async def stream(self, messages, **kwargs):
            yield "stubbed"

        async def embed(self, texts, **kwargs):
            return [[0.0] for _ in texts]

    import app.llm.providers.openai as openai_mod
    monkeypatch.setattr(openai_mod, "OpenAIProvider", lambda *a, **k: _StubLLM())

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_sqlite):
    return TestClient(app_with_sqlite)


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_admin_tools_list(client):
    r = client.get("/api/v1/admin/tools")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "calculator" in names
    assert "web_search" in names
    assert "sql_query" in names


def test_admin_metrics(client):
    r = client.get("/api/v1/admin/metrics")
    assert r.status_code == 200
    assert "counters" in r.json()


def test_auth_login_dev(client):
    r = client.post("/api/v1/auth/login", json={"username": "tester", "password": ""})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["role"] == "user"


def test_auth_me_dev(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_sessions_list(client):
    r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_audit_list(client):
    r = client.get("/api/v1/audit")
    assert r.status_code == 200


def test_evals_results_list(client):
    r = client.get("/api/v1/evals/results")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
