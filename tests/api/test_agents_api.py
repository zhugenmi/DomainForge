"""Tests for agents CRUD API."""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.category import Category


@pytest.fixture
def app_with_db(monkeypatch):
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
            for name in ["legal", "finance"]:
                s.add(Category(name=name, is_builtin=True))
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

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_db):
    with TestClient(app_with_db) as c:
        yield c


def test_list_agents_empty_initially(client):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_agent_success(client):
    payload = {
        "name": "我的助手",
        "description": "测试",
        "system_prompt": "你是助手",
        "model_name": "gpt-4o-mini",
        "temperature": 0.5,
        "domain": "legal",
    }
    resp = client.post("/api/v1/agents", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "我的助手"
    assert body["is_builtin"] is False
    assert body["domain"] == "legal"


def test_create_agent_invalid_domain_returns_404(client):
    payload = {
        "name": "x",
        "model_name": "gpt-4o-mini",
        "domain": "nonexistent",
    }
    resp = client.post("/api/v1/agents", json=payload)
    assert resp.status_code == 404


def test_create_agent_forces_non_builtin(client):
    payload = {
        "name": "fake builtin",
        "model_name": "gpt-4o-mini",
        "is_builtin": True,
    }
    resp = client.post("/api/v1/agents", json=payload)
    assert resp.status_code == 201
    assert resp.json()["is_builtin"] is False


def test_update_agent(client):
    create = client.post(
        "/api/v1/agents",
        json={"name": "u", "model_name": "gpt-4o-mini"},
    )
    aid = create.json()["id"]
    resp = client.put(f"/api/v1/agents/{aid}", json={"description": "updated"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "updated"


def test_delete_custom_agent(client):
    create = client.post(
        "/api/v1/agents",
        json={"name": "del", "model_name": "gpt-4o-mini"},
    )
    aid = create.json()["id"]
    resp = client.delete(f"/api/v1/agents/{aid}")
    assert resp.status_code == 204


def test_delete_builtin_agent_returns_403(client, app_with_db):
    from app.database.models.agent import Agent

    create = client.post(
        "/api/v1/agents",
        json={"name": "builtin-test", "model_name": "gpt-4o-mini"},
    )
    aid = create.json()["id"]

    async def _mark_builtin():
        from app.main import app
        get_db = __import__("app.database.session", fromlist=["get_db"]).get_db
        gen = app.dependency_overrides[get_db]()
        db = await gen.__anext__()
        agent = await db.get(Agent, uuid.UUID(aid))
        agent.is_builtin = True
        await db.commit()

    asyncio.run(_mark_builtin())
    resp = client.delete(f"/api/v1/agents/{aid}")
    assert resp.status_code == 403
