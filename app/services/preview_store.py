from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.observability.logging.logger import get_logger

logger = get_logger("preview_store")


class PreviewStore:
    """进程内 TTL 存储用于"已解析未确认"的上传会话。

    session 数据结构：
    {
        "domain": str,
        "chunk_strategy": str,
        "chunk_size": int,
        "chunk_overlap": int,
        "files": [
            {
                "filename": str,
                "file_type": str,
                "file_size_bytes": int,
                "parsed_text": str,
                "chunks": [str, ...],
                "word_count": int,
            },
            ...
        ],
    }
    """

    def __init__(self, ttl: int = 600):
        self.ttl = ttl
        self._store: dict[uuid.UUID, dict[str, Any]] = {}
        self._expiry: dict[uuid.UUID, float] = {}
        self._lock = asyncio.Lock()

    async def put(self, session_id: uuid.UUID, data: dict[str, Any]) -> None:
        async with self._lock:
            self._store[session_id] = data
            self._expiry[session_id] = time.time() + self.ttl

    async def get(self, session_id: uuid.UUID) -> dict[str, Any] | None:
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
        async with self._lock:
            self._store.pop(session_id, None)
            self._expiry.pop(session_id, None)

    async def sweep(self) -> int:
        """清理所有过期会话，返回清理数量。"""
        now = time.time()
        expired = [sid for sid, exp in self._expiry.items() if now > exp]
        async with self._lock:
            for sid in expired:
                self._store.pop(sid, None)
                self._expiry.pop(sid, None)
        if expired:
            logger.info("preview_sweep", removed=len(expired))
        return len(expired)


preview_store = PreviewStore()


async def run_periodic_sweep(interval: int = 60) -> None:
    """周期清理过期 preview session。在 lifespan 中作为后台任务启动。"""
    while True:
        try:
            await asyncio.sleep(interval)
            await preview_store.sweep()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("preview_sweep_failed", error=str(e))


__all__ = ["PreviewStore", "preview_store", "run_periodic_sweep"]
