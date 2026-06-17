from __future__ import annotations

import json

from app.llm.base import LLMProvider
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
        tools = self.tool_registry.get_openai_tools()
        if not tools:
            return state

        messages = state.messages + [{"role": "user", "content": state.query}]
        response = await self.llm.client.chat.completions.create(
            model=self.llm.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        if not message.tool_calls:
            return state

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            await self.event_bus.publish(SSEEventType.TOOL_CALLED, {"tool": fn_name, "args": fn_args})

            tool = self.tool_registry.get(fn_name)
            if tool:
                result = await tool.execute(**fn_args)
                state.tool_results.append({"tool": fn_name, "result": result})
                await self.event_bus.publish(SSEEventType.TOOL_RESULT, {"tool": fn_name, "result": result})

        return state
