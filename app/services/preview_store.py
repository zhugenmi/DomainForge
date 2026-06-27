from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from app.observability.logging.logger import get_logger
from app.services.redis import get_redis

logger = get_logger("preview_store")


class PreviewStore:
    """已解析未确认的上传会话存储。

    Redis 可用时用 Redis hash + TTL（多 worker 共享）；不可用退化为进程内 dict。
    接口不变，调用方无感。
    """

    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        # 进程内退路
        self._store: dict[uuid.UUID, dict[str, Any]] = {}
        self._expiry: dict[uuid.UUID, float] = {}
        self._lock = asyncio.Lock()

    async def put(self, session_id: uuid.UUID, data: dict[str, Any]) -> None:
        r = await get_redis()
        if r is not None:
            try:
                await r.set(self._redis_key(session_id), json.dumps(data, ensure_ascii=False), ex=self.ttl)
                return
            except Exception as e:
                logger.warning("preview_redis_put_failed", error=str(e), fallback="in-memory")
        async with self._lock:
            self._store[session_id] = data
            self._expiry[session_id] = time.time() + self.ttl

    async def get(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        r = await get_redis()
        if r is not None:
            try:
                raw = await r.get(self._redis_key(session_id))
                if raw is None:
                    return None
                return json.loads(raw)
            except Exception as e:
                logger.warning("preview_redis_get_failed", error=str(e), fallback="in-memory")
        async with self._lock:
            exp = self._expiry.get(session_id)
            if exp is None:
                return None
            if time.time() > exp:
                self._store.pop(session_id, None)
                self._expiry.pop(session_id, None)
                logger.info("preview_expired_on_read", session_id=str(session_id))
                return None
            return self._store.get(session_id)

    async def remove(self, session_id: uuid.UUID) -> None:
        r = await get_redis()
        if r is not None:
            try:
                await r.delete(self._redis_key(session_id))
            except Exception:
                pass
        async with self._lock:
            self._store.pop(session_id, None)
            self._expiry.pop(session_id, None)

    async def sweep(self) -> int:
        """Redis 模式下 TTL 自动清理，此方法仅清理进程内退路的过期项。"""
        now = time.time()
        expired = [sid for sid, exp in self._expiry.items() if now > exp]
        async with self._lock:
            for sid in expired:
                self._store.pop(sid, None)
                self._expiry.pop(sid, None)
        if expired:
            logger.info("preview_sweep", removed=len(expired))
        return len(expired)

    @staticmethod
    def _redis_key(session_id: uuid.UUID) -> str:
        return f"preview:{session_id}"


preview_store = PreviewStore()


async def run_periodic_sweep(interval: int = 60) -> None:
    """周期清理过期 preview session（进程内退路）。Redis 模式下 no-op。"""
    while True:
        try:
            await asyncio.sleep(interval)
            await preview_store.sweep()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("preview_sweep_failed", error=str(e))


__all__ = ["PreviewStore", "preview_store", "run_periodic_sweep"]
