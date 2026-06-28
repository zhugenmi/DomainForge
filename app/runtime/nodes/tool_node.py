from __future__ import annotations

import json
import time

from app.configs.settings import settings
from app.llm.base import LLMProvider, ToolCall
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry

TOOL_SYSTEM_PROMPT = """你是一个能调用工具的助手。根据用户问题决定是否调用工具：

- 需要外部信息（天气、搜索、计算、知识库等）时，调用对应工具
- 工具返回结果后，基于结果继续回答或调用更多工具
- 信息充分时，直接给出最终自然语言回答，不再调用工具
- 不要输出函数调用标记或 JSON，工具调用由系统处理"""


class ToolNode(BaseNode):
    """ReAct 工具循环节点。

    每轮：chat_with_tools → 若有 tool_call 则执行并把结果作为 tool 消息塞回 → 继续；
    LLM 不再发 tool_call 时，其 content 作为最终答案写入 state，AnswerNode 跳过。
    敏感工具需二次确认时暂挂，等客户端确认后恢复。
    """

    def __init__(self, llm: LLMProvider, tool_registry: ToolRegistry, event_bus: EventBus):
        self.llm = llm
        self.tool_registry = tool_registry
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        tools = self.tool_registry.get_openai_tools()
        if not tools:
            return state

        # 恢复暂挂的 tool_calls（敏感工具确认后）
        pending: list[ToolCall] = list(state.pending_tool_calls)
        state.pending_tool_calls = []

        messages: list[dict] = (
            [{"role": "system", "content": TOOL_SYSTEM_PROMPT}]
            + state.messages
            + [{"role": "user", "content": state.query}]
            + state.tool_messages
        )

        for iteration in range(state.max_tool_iterations):
            calls = pending
            pending = []
            if not calls:
                try:
                    response = await self.llm.chat_with_tools(
                        messages=messages, tools=tools, tool_choice="auto"
                    )
                except NotImplementedError:
                    return state
                if response is None:
                    return state
                calls = response.tool_calls or []
                if not calls:
                    await self._maybe_finalize(state, response.content)
                    return state

            # 暂挂超时检查
            if state.pending_since and time.time() - state.pending_since > settings.SENSITIVE_TOOL_CONFIRM_TIMEOUT:
                for tc in calls:
                    state.tool_results.append({"tool": tc.name, "result": {"skipped": True, "reason": "confirm_timeout"}})
                    await self.event_bus.publish(
                        SSEEventType.TOOL_RESULT, {"tool": tc.name, "result": {"skipped": True, "reason": "confirm_timeout"}}
                    )
                state.pending_since = 0.0
                return state

            # 敏感工具确认闸门
            confirmed_now, deferred = self._split_sensitive(state, calls)
            if deferred:
                state.pending_tool_calls = deferred
                state.pending_since = time.time()
                await self.event_bus.publish(
                    SSEEventType.TOOL_CONFIRM_REQUIRED,
                    {"tool": deferred[0].name, "args": deferred[0].arguments},
                )
                return state

            if not confirmed_now:
                return state

            assistant_msg = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                    for tc in confirmed_now
                ],
            }
            messages.append(assistant_msg)

            for tc in confirmed_now:
                await self.event_bus.publish(SSEEventType.TOOL_CALLED, {"tool": tc.name, "args": tc.arguments})
                tool = self.tool_registry.get(tc.name)
                if tool is None:
                    result = {"error": f"未知工具: {tc.name}"}
                else:
                    try:
                        result = await tool.execute(**tc.arguments)
                    except Exception as e:
                        result = {"error": str(e)}
                state.tool_results.append({"tool": tc.name, "result": result})
                await self.event_bus.publish(SSEEventType.TOOL_RESULT, {"tool": tc.name, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
                state.tool_messages.append(messages[-1])
                state.tool_messages.append(assistant_msg)

        state.pending_since = 0.0
        return state

    def _split_sensitive(
        self, state: AgentState, calls: list[ToolCall]
    ) -> tuple[list[ToolCall], list[ToolCall]]:
        """切分已确认可执行 vs 需暂挂确认的敏感调用。

        首个未确认的敏感调用及其后全部暂挂；已确认的敏感 + 所有非敏感立即可执行。
        """
        ready: list[ToolCall] = []
        deferred: list[ToolCall] = []
        deferred_mode = False
        for tc in calls:
            tool = self.tool_registry.get(tc.name)
            is_sensitive = tool is not None and tool.permission_scope == "sensitive"
            if deferred_mode or (is_sensitive and tc.name not in state.confirmed_tool_names):
                deferred.append(tc)
                deferred_mode = True
            else:
                ready.append(tc)
        return ready, deferred

    async def _maybe_finalize(self, state: AgentState, content: str) -> None:
        """LLM 在 tool 循环中直接给出文本答案（无后续 tool_call）时收尾。"""
        if not content.strip():
            return
        state.final_answer = content
        state.answered_by_tool = True
        await self.event_bus.publish(
            SSEEventType.FINAL_ANSWER, {"answer": content, "citations": state.citations}
        )


__all__ = ["ToolNode"]
