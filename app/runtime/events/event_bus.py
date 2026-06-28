from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from app.runtime.events.event_type import SSEEventType


class EventBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def publish(self, event_type: SSEEventType, data: dict[str, Any] | None = None) -> None:
        # default=str 兜底：tool 结果里常带 datetime/UUID/dataclass 等非原生类型，
        # 不转字符串会让 SSE 流整个挂掉（用户看到 [生成失败：未获得回复]）。
        payload = json.dumps(
            {"event": event_type.value, "data": data or {}}, ensure_ascii=False, default=str
        )
        await self._queue.put(payload)

    async def publish_error(self, message: str) -> None:
        payload = json.dumps({"event": SSEEventType.ERROR.value, "data": {"message": message}}, ensure_ascii=False)
        await self._queue.put(payload)

    def done(self) -> None:
        self._queue.put_nowait(None)

    async def stream(self) -> AsyncGenerator[str, None]:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield f"data: {item}\n\n"
