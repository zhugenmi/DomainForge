"""模块 04 后端 Redis：缓存、限流、PreviewStore Redis 后端。

Redis 未运行，用 FakeRedis（in-memory 模拟 asyncio Redis 接口）测试 Redis 路径；
并测试降级路径（REDIS_ENABLED=false → 无 Redis 行为）。

用 sync 测试 + 独立 event loop（asyncio.new_event_loop）跑 async 代码，
避免干扰后续测试文件的 event loop 状态。
"""
import asyncio
import time
import uuid

import pytest

import app.database.models  # noqa: F401  确保 Base.metadata 注册所有表
from app.services import redis as redis_mod


def run(coro):
    """独立 loop 跑 async 代码，跑完即关，不污染全局 loop 状态。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeRedis:
    """最小 in-memory Redis 模拟，覆盖 get/set/delete/expire/scan_iter/pipeline/zset。"""

    def __init__(self):
        self._store: dict[str, str] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._ttl: dict[str, float] = {}

    async def ping(self):
        return True

    async def get(self, k):
        if self._expired(k):
            self._store.pop(k, None)
            return None
        return self._store.get(k)

    async def set(self, k, v, ex=None):
        self._store[k] = v
        if ex:
            self._ttl[k] = time.time() + ex
        return True

    async def delete(self, k):
        self._store.pop(k, None)
        self._ttl.pop(k, None)
        self._zsets.pop(k, None)
        return 1

    async def expire(self, k, secs):
        if k in self._store:
            self._ttl[k] = time.time() + secs
        return True

    def pipeline(self):
        return _FakePipeline(self)

    async def zadd(self, k, mapping):
        self._zsets.setdefault(k, {}).update(mapping)
        return len(mapping)

    async def zremrangebyscore(self, k, lo, hi):
        zs = self._zsets.get(k, {})
        removed = [m for m, s in zs.items() if lo <= s <= hi]
        for m in removed:
            zs.pop(m, None)
        return len(removed)

    async def zcard(self, k):
        return len(self._zsets.get(k, {}))

    async def scan_iter(self, match=None, count=100):
        for k in list(self._store.keys()):
            if match is None or self._match(match, k):
                yield k

    @staticmethod
    def _match(pattern, key):
        import fnmatch

        return fnmatch.fnmatch(key, pattern)

    def _expired(self, k) -> bool:
        return k in self._ttl and time.time() > self._ttl[k]

    async def aclose(self):
        pass


class _FakePipeline:
    def __init__(self, redis: FakeRedis):
        self._r = redis
        self._ops: list = []

    def zremrangebyscore(self, k, lo, hi):
        self._ops.append(("zremrangebyscore", k, lo, hi))
        return self

    def zadd(self, k, mapping):
        self._ops.append(("zadd", k, mapping))
        return self

    def zcard(self, k):
        self._ops.append(("zcard", k))
        return self

    def expire(self, k, secs):
        self._ops.append(("expire", k, secs))
        return self

    async def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "zremrangebyscore":
                results.append(await self._r.zremrangebyscore(op[1], op[2], op[3]))
            elif op[0] == "zadd":
                results.append(await self._r.zadd(op[1], op[2]))
            elif op[0] == "zcard":
                results.append(await self._r.zcard(op[1]))
            elif op[0] == "expire":
                results.append(await self._r.expire(op[1], op[2]))
        return results


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_mod, "_client", fake)
    monkeypatch.setattr(redis_mod, "_initialized", True)
    return fake


@pytest.fixture
def no_redis(monkeypatch):
    monkeypatch.setattr(redis_mod, "_client", None)
    monkeypatch.setattr(redis_mod, "_initialized", True)


# ---------- cache 工具 ----------

def test_cache_set_get(fake_redis):
    from app.services.cache import cache_get, cache_set

    run(cache_set("ns", {"a": 1}, 60, "k1"))
    out = run(cache_get("ns", "k1"))
    assert out == {"a": 1}


def test_cache_get_miss(fake_redis):
    from app.services.cache import cache_get

    assert run(cache_get("ns", "missing")) is None


def test_cache_clear_prefix(fake_redis):
    from app.services.cache import cache_set, cache_clear_prefix, cache_get

    run(cache_set("chat", {"x": 1}, 60, "a"))
    run(cache_set("chat", {"x": 2}, 60, "b"))
    run(cache_set("rag", {"y": 1}, 60, "c"))
    removed = run(cache_clear_prefix("chat:"))
    assert removed == 2
    assert run(cache_get("chat", "a")) is None
    assert run(cache_get("rag", "c")) is not None


def test_cache_noop_when_redis_disabled(no_redis):
    from app.services.cache import cache_get, cache_set

    assert run(cache_get("ns", "k")) is None
    run(cache_set("ns", {"a": 1}, 60, "k"))  # 不抛错


# ---------- PreviewStore Redis ----------

def test_preview_store_redis_put_get(fake_redis):
    from app.services.preview_store import PreviewStore

    store = PreviewStore(ttl=60)
    sid = uuid.uuid4()
    run(store.put(sid, {"domain": "legal", "files": []}))
    out = run(store.get(sid))
    assert out == {"domain": "legal", "files": []}


def test_preview_store_redis_remove(fake_redis):
    from app.services.preview_store import PreviewStore

    store = PreviewStore(ttl=60)
    sid = uuid.uuid4()
    run(store.put(sid, {"domain": "legal"}))
    run(store.remove(sid))
    assert run(store.get(sid)) is None


def test_preview_store_fallback_to_inmemory(no_redis):
    from app.services.preview_store import PreviewStore

    store = PreviewStore(ttl=60)
    sid = uuid.uuid4()
    run(store.put(sid, {"domain": "legal"}))
    assert run(store.get(sid)) == {"domain": "legal"}


def test_preview_store_inmemory_expiry(no_redis):
    from app.services.preview_store import PreviewStore

    store = PreviewStore(ttl=0)
    sid = uuid.uuid4()
    run(store.put(sid, {"domain": "legal"}))
    time.sleep(0.01)
    assert run(store.get(sid)) is None


# ---------- 限流 ----------

def test_rate_limit_route_groups():
    from app.api.middleware.rate_limit import _match_group

    assert _match_group("/api/v1/chat") == ("/api/v1/chat", 20, 60)
    assert _match_group("/api/v1/knowledge/search") == ("/api/v1/knowledge/search", 60, 60)
    assert _match_group("/api/v1/health") is None


def test_rate_limit_429_over_quota(fake_redis):
    """同一 IP 超 20 次/分钟，第 21 次限流。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.middleware.rate_limit import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/chat")
    async def _chat():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(20):
        r = client.get("/api/v1/chat")
        assert r.status_code == 200
    r = client.get("/api/v1/chat")
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "60"


def test_rate_limit_passes_when_redis_disabled(no_redis):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.middleware.rate_limit import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/v1/chat")
    async def _chat():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(30):
        assert client.get("/api/v1/chat").status_code == 200  # 无 Redis 不限流
