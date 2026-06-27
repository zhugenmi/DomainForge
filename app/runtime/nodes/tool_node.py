from __future__ import annotations

import time

from app.configs.settings import settings
from app.llm.base import LLMProvider, ToolCall
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry


class ToolNode(BaseNode):
    def __init__(self, llm: LLMProvider, tool_registry: ToolRegistry, event_bus: EventBus):
        self.llm = llm
        self.tool_registry = tool_registry
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        if state.intent != "tool":
            return state

        # 恢复上次因等待确认而暂挂的 tool_calls；无则向 LLM 申请新的
        calls: list[ToolCall] = list(state.pending_tool_calls)
        state.pending_tool_calls = []

        if not calls:
            tools = self.tool_registry.get_openai_tools()
            if not tools:
                return state
            messages = state.messages + [{"role": "user", "content": state.query}]
            response = await self.llm.chat_with_tools(
                messages=messages, tools=tools, tool_choice="auto"
            )
            calls = response.tool_calls or []

        if not calls:
            return state

        # 暂挂超时检查：上轮挂起的 sensitive 调用若超时仍未确认，标 skipped
        if state.pending_since and time.time() - state.pending_since > settings.SENSITIVE_TOOL_CONFIRM_TIMEOUT:
            for tc in calls:
                state.tool_results.append({"tool": tc.name, "result": {"skipped": True, "reason": "confirm_timeout"}})
                await self.event_bus.publish(
                    SSEEventType.TOOL_RESULT, {"tool": tc.name, "result": {"skipped": True, "reason": "confirm_timeout"}}
                )
            return state

        for i, tc in enumerate(calls):
            tool = self.tool_registry.get(tc.name)
            if tool is None:
                continue
            if (
                tool.permission_scope == "sensitive"
                and tc.name not in state.confirmed_tool_names
            ):
                # 暂挂当前及后续 tool_call，发确认事件，提前返回
                state.pending_tool_calls = calls[i:]
                state.pending_since = time.time()
                await self.event_bus.publish(
                    SSEEventType.TOOL_CONFIRM_REQUIRED,
                    {"tool": tc.name, "args": tc.arguments},
                )
                return state

            await self.event_bus.publish(SSEEventType.TOOL_CALLED, {"tool": tc.name, "args": tc.arguments})
            result = await tool.execute(**tc.arguments)
            state.tool_results.append({"tool": tc.name, "result": result})
            await self.event_bus.publish(SSEEventType.TOOL_RESULT, {"tool": tc.name, "result": result})

        state.pending_since = 0.0
        return state


__all__ = ["ToolNode"]
