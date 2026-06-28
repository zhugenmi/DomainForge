"""模块 06 安全加固：prod 登录校验 + login/logout 审计。"""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.audit_log import AuditLog
from app.database.repositories.user_repo import UserRepo


def _build_app(env: str, *, seed_user: tuple[str, str] | None = None, admin_key: str = ""):
    """构造一个 sqlite 内存库 app，并把 settings 切到指定 env。"""
    from app.configs import settings as settings_mod

    settings_mod.settings.APP_ENV = env
    settings_mod.settings.JWT_SECRET = "a" * 32 if env == "prod" else settings_mod.settings.JWT_SECRET
    settings_mod.settings.ADMIN_API_KEY = admin_key

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        if seed_user:
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as s:
                await UserRepo(s).create(username=seed_user[0], role="user", password=seed_user[1])
                await s.commit()

    asyncio.run(_init())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    from app.database.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = _get_db
    return app, factory


@pytest.fixture
def prod_app_with_user(monkeypatch):
    # 保存并恢复 settings 单例字段
    from app.configs import settings as settings_mod

    originals = {
        "APP_ENV": settings_mod.settings.APP_ENV,
        "JWT_SECRET": settings_mod.settings.JWT_SECRET,
        "ADMIN_API_KEY": settings_mod.settings.ADMIN_API_KEY,
    }
    app, factory = _build_app("prod", seed_user=("alice", "alice-pw"))
    yield app, factory
    for k, v in originals.items():
        setattr(settings_mod.settings, k, v)
    app.dependency_overrides.clear()


@pytest.fixture
def dev_app(monkeypatch):
    from app.configs import settings as settings_mod

    originals = {
        "APP_ENV": settings_mod.settings.APP_ENV,
        "JWT_SECRET": settings_mod.settings.JWT_SECRET,
        "ADMIN_API_KEY": settings_mod.settings.ADMIN_API_KEY,
    }
    app, factory = _build_app("dev")
    yield app, factory
    for k, v in originals.items():
        setattr(settings_mod.settings, k, v)
    app.dependency_overrides.clear()


def test_login_prod_rejects_missing_password(prod_app_with_user):
    app, _ = prod_app_with_user
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": ""})
    assert r.status_code == 401


def test_login_prod_rejects_bad_password(prod_app_with_user):
    app, _ = prod_app_with_user
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


def test_login_prod_accepts_correct_password(prod_app_with_user):
    app, _ = prod_app_with_user
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice-pw"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["role"] == "user"


def test_login_prod_admin_via_admin_key(prod_app_with_user, monkeypatch):
    from app.configs import settings as settings_mod

    settings_mod.settings.ADMIN_API_KEY = "secret-admin-key"
    app, _ = prod_app_with_user
    client = TestClient(app)
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "alice-pw", "admin_key": "secret-admin-key"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_login_success_audited(prod_app_with_user):
    app, factory = prod_app_with_user
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"username": "alice", "password": "alice-pw"})

    async def _read():
        async with factory() as s:
            res = await s.execute(select(AuditLog).where(AuditLog.action == "login_success"))
            return list(res.scalars().all())

    logs = asyncio.run(_read())
    assert len(logs) == 1
    payload = logs[0].payload
    assert payload["username"] == "alice"
    assert payload["ip"]
    # 审计不得记录密码
    assert "password" not in payload


def test_login_failed_audited(prod_app_with_user):
    app, factory = prod_app_with_user
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong"})

    async def _read():
        async with factory() as s:
            res = await s.execute(select(AuditLog).where(AuditLog.action == "login_failed"))
            return list(res.scalars().all())

    logs = asyncio.run(_read())
    assert len(logs) == 1
    assert logs[0].payload["reason"] == "bad_credentials"


def test_login_dev_any_user_still_works(dev_app):
    app, _ = dev_app
    client = TestClient(app)
    r = client.post("/api/v1/auth/login", json={"username": "tester", "password": ""})
    assert r.status_code == 200
    assert r.json()["role"] == "user"


def test_logout_audited(dev_app):
    app, factory = dev_app
    client = TestClient(app)
    token = client.post("/api/v1/auth/login", json={"username": "tester"}).json()["access_token"]
    r = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    async def _read():
        async with factory() as s:
            res = await s.execute(select(AuditLog).where(AuditLog.action == "logout"))
            return list(res.scalars().all())

    logs = asyncio.run(_read())
    assert len(logs) == 1
    assert logs[0].payload["username"] == "tester"
