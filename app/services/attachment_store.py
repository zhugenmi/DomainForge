from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.configs.settings import settings
from app.observability.logging.logger import get_logger

logger = get_logger("attachment_store")


class AttachmentStore:
    """聊天附件的进程内临时存储。

    预上传时写入，chat 调用 pop_many 取出并删除；TTL 兜底防止泄漏。
    不走 Redis：附件是单会话短命对象，进程内即可。
    """

    def __init__(self, ttl: int | None = None):
        self.ttl = ttl if ttl is not None else settings.CHAT_ATTACHMENT_TTL
        self._store: dict[uuid.UUID, dict[str, Any]] = {}
        self._expiry: dict[uuid.UUID, float] = {}
        self._lock = asyncio.Lock()

    async def put(self, filename: str, content: str) -> uuid.UUID:
        aid = uuid.uuid4()
        async with self._lock:
            self._store[aid] = {"filename": filename, "content": content}
            self._expiry[aid] = time.time() + self.ttl
        return aid

    async def get(self, aid: uuid.UUID) -> dict[str, Any] | None:
        async with self._lock:
            exp = self._expiry.get(aid)
            if exp is None:
                return None
            if time.time() > exp:
                self._store.pop(aid, None)
                self._expiry.pop(aid, None)
                return None
            return self._store.get(aid)

    async def pop_many(self, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        async with self._lock:
            now = time.time()
            for aid in ids:
                exp = self._expiry.get(aid)
                if exp is None or now > exp:
                    self._store.pop(aid, None)
                    self._expiry.pop(aid, None)
                    continue
                item = self._store.pop(aid, None)
                self._expiry.pop(aid, None)
                if item is not None:
                    out.append(item)
        return out

    async def sweep(self) -> int:
        now = time.time()
        async with self._lock:
            expired = [aid for aid, exp in self._expiry.items() if now > exp]
            for aid in expired:
                self._store.pop(aid, None)
                self._expiry.pop(aid, None)
        if expired:
            logger.info("attachment_sweep", removed=len(expired))
        return len(expired)


attachment_store = AttachmentStore()


__all__ = ["AttachmentStore", "attachment_store"]
