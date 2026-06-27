import asyncio

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

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_session_with_agent_id(client):
    agent_id = client.get("/api/v1/agents").json()[0]["id"]
    resp = client.post("/api/v1/sessions", json={"agent_id": agent_id})
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["agent_id"] == agent_id


def test_update_session_agent(client):
    create = client.post("/api/v1/sessions", json={})
    sid = create.json()["id"]
    agent_id = client.get("/api/v1/agents").json()[0]["id"]
    resp = client.put(f"/api/v1/sessions/{sid}", json={"agent_id": agent_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent_id"] == agent_id


def test_list_sessions_includes_agent_id(client):
    agent_id = client.get("/api/v1/agents").json()[0]["id"]
    client.post("/api/v1/sessions", json={"agent_id": agent_id})
    lst = client.get("/api/v1/sessions").json()
    assert any(s.get("agent_id") == agent_id for s in lst)
