"""Redis 缓存工具。Redis 不可用时所有操作 no-op，调用方无感降级。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.observability.logging.logger import get_logger
from app.services.redis import get_redis

logger = get_logger("cache")


def _key(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def cache_get(namespace: str, *parts: str) -> Any | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        k = f"{namespace}:{_key(*parts)}"
        raw = await r.get(k)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("cache_get_failed", error=str(e))
        return None


async def cache_set(namespace: str, value: Any, ttl: int, *parts: str) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        k = f"{namespace}:{_key(*parts)}"
        await r.set(k, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:
        logger.warning("cache_set_failed", error=str(e))


async def cache_clear_prefix(prefix: str) -> int:
    """删除匹配前缀的所有 key，返回删除数。"""
    r = await get_redis()
    if r is None:
        return 0
    try:
        count = 0
        async for k in r.scan_iter(match=f"{prefix}*", count=100):
            await r.delete(k)
            count += 1
        return count
    except Exception as e:
        logger.warning("cache_clear_failed", prefix=prefix, error=str(e))
        return 0


__all__ = ["cache_get", "cache_set", "cache_clear_prefix"]
