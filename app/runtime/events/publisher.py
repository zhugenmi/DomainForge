from __future__ import annotations

from typing import Any

from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType


class EventPublisher:
    """对 EventBus 的语义化封装，便于在 runtime/audit 多处复用。"""

    def __init__(self, bus: EventBus):
        self.bus = bus

    async def intent(self, intent: str) -> None:
        await self.bus.publish(SSEEventType.INTENT_DETECTED, {"intent": intent})

    async def plan(self, steps: list[str]) -> None:
        await self.bus.publish(SSEEventType.PLAN_GENERATED, {"steps": steps})

    async def retrieval(self, query: str) -> None:
        await self.bus.publish(SSEEventType.RETRIEVAL_STARTED, {"query": query})

    async def tool_call(self, tool: str, args: dict[str, Any]) -> None:
        await self.bus.publish(SSEEventType.TOOL_CALLED, {"tool": tool, "args": args})

    async def tool_result(self, tool: str, result: Any) -> None:
        await self.bus.publish(SSEEventType.TOOL_RESULT, {"tool": tool, "result": result})

    async def reflection(self, verdict: dict) -> None:
        await self.bus.publish(SSEEventType.REFLECTION, verdict)

    async def answer(self, answer: str) -> None:
        await self.bus.publish(SSEEventType.FINAL_ANSWER, {"answer": answer})

    async def error(self, message: str) -> None:
        await self.bus.publish_error(message)


__all__ = ["EventPublisher"]
