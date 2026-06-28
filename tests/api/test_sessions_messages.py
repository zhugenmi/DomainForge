import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.session import Session as SessionModel
from app.database.models.user import User as UserModel


@pytest.fixture
def app_with_sqlite(monkeypatch):
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
            s.add(UserModel(id=uuid.uuid4(), username="default"))
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

    import app.database.session as dbsess
    monkeypatch.setattr(dbsess, "async_session_factory", factory)

    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_sqlite):
    return TestClient(app_with_sqlite)


def test_message_citations_persisted_and_returned(client, app_with_sqlite):
    from app.database.models.session import Session as SessionModel
    import app.database.session as dbsess

    async def _seed():
        async with dbsess.async_session_factory() as s:
            from app.database.models.message import Message
            # Get existing user
            from sqlalchemy import select
            from app.database.models.user import User as UserModel
            result = await s.execute(select(UserModel).limit(1))
            user = result.scalars().first()
            sess = SessionModel(id=uuid.uuid4(), user_id=user.id, agent_id=None)
            s.add(sess)
            await s.flush()
            s.add(Message(
                session_id=sess.id, role="assistant", content="回答[1]",
                citations=[{"index": 1, "title": "民法典.txt", "locator": "第三条",
                            "snippet": "内容", "document_id": "d1", "chunk_id": "c1"}],
            ))
            await s.commit()
            return str(sess.id)

    loop = asyncio.new_event_loop()
    sid = loop.run_until_complete(_seed())
    loop.close()

    r = client.get(f"/api/v1/sessions/{sid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 1
    asst = [m for m in msgs if m["role"] == "assistant"][0]
    assert asst["citations"] is not None
    assert len(asst["citations"]) == 1
    assert asst["citations"][0]["title"] == "民法典.txt"
    assert asst["citations"][0]["locator"] == "第三条"
