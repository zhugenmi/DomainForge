"""ToolNode ReAct 循环测试：直接答、单轮 tool、多轮 tool、达上限、敏感确认。"""
from __future__ import annotations

import pytest

from app.llm.base import LLMProvider, ToolCall, ToolCallResponse
from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.tool_node import ToolNode
from app.runtime.state.agent_state import AgentState
from app.tools.base import Tool
from app.tools.registry.registry import ToolRegistry
from app.tools.registry.schema import ToolParameter, ToolSchema


class _ScriptedProvider(LLMProvider):
    """按脚本依次返回 ToolCallResponse；超出脚本后返回空 tool_calls。"""

    def __init__(self, script: list[ToolCallResponse]):
        self.model = "stub-scripted"
        self._script = list(script)
        self._i = 0

    async def generate(self, messages, **kwargs):
        return "ok"

    async def stream(self, messages, **kwargs):
        yield "ok"

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]

    async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
        if self._i < len(self._script):
            resp = self._script[self._i]
            self._i += 1
            return resp
        return ToolCallResponse(content="", tool_calls=[])


class _EchoTool(Tool):
    name = "echo"
    description = "echo args back"
    schema = ToolSchema(parameters=[ToolParameter(name="msg", type="string", required=True)])
    permission_scope = "default"

    async def execute(self, **kwargs):
        return kwargs.get("msg")


class _CounterTool(Tool):
    """每次调用返回当前调用次数，用于验证多轮。"""
    name = "counter"
    description = "return call count"
    schema = ToolSchema(parameters=[])
    permission_scope = "default"

    def __init__(self):
        self.n = 0

    async def execute(self, **kwargs):
        self.n += 1
        return self.n


def _registry(*tools: Tool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


@pytest.mark.asyncio
async def test_react_no_tool_call_finalizes_answer():
    """LLM 第一轮就给文本答案、不发 tool_call → 直接写入 final_answer，AnswerNode 应跳过。"""
    bus = EventBus()
    reg = _registry(_EchoTool())
    provider = _ScriptedProvider([ToolCallResponse(content="成都现在 ⛅️ 8°C", tool_calls=[])])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="成都天气")
    state = await node.execute(state)

    assert state.answered_by_tool is True
    assert state.final_answer == "成都现在 ⛅️ 8°C"
    assert state.tool_results == []


@pytest.mark.asyncio
async def test_react_single_tool_then_answer():
    """LLM 第一轮调 echo，第二轮基于结果直接答。"""
    bus = EventBus()
    reg = _registry(_EchoTool())
    provider = _ScriptedProvider([
        ToolCallResponse(content="", tool_calls=[ToolCall(id="1", name="echo", arguments={"msg": "hi"})]),
        ToolCallResponse(content="echoed: hi", tool_calls=[]),
    ])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="echo hi")
    state = await node.execute(state)

    assert state.tool_results == [{"tool": "echo", "result": "hi"}]
    assert state.answered_by_tool is True
    assert state.final_answer == "echoed: hi"


@pytest.mark.asyncio
async def test_react_multi_tool_iterations():
    """LLM 连续两轮各调一次 counter，第三轮直接答。"""
    bus = EventBus()
    counter = _CounterTool()
    reg = _registry(counter)
    provider = _ScriptedProvider([
        ToolCallResponse(content="", tool_calls=[ToolCall(id="1", name="counter", arguments={})]),
        ToolCallResponse(content="", tool_calls=[ToolCall(id="2", name="counter", arguments={})]),
        ToolCallResponse(content="counted twice", tool_calls=[]),
    ])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="count twice")
    state = await node.execute(state)

    assert counter.n == 2
    assert len(state.tool_results) == 2
    assert state.tool_results[0]["result"] == 1
    assert state.tool_results[1]["result"] == 2
    assert state.final_answer == "counted twice"


@pytest.mark.asyncio
async def test_react_hits_iteration_limit():
    """LLM 每轮都发 tool_call，达到 max_tool_iterations 后停止，不写 final_answer。"""
    bus = EventBus()
    counter = _CounterTool()
    reg = _registry(counter)
    # 每轮都调 counter，永不停止
    loop_resp = ToolCallResponse(content="", tool_calls=[ToolCall(id="x", name="counter", arguments={})])
    provider = _ScriptedProvider([loop_resp, loop_resp, loop_resp, loop_resp, loop_resp])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="loop")
    state.max_tool_iterations = 3
    state = await node.execute(state)

    assert counter.n == 3
    assert state.answered_by_tool is False
    assert state.final_answer == ""


@pytest.mark.asyncio
async def test_react_unknown_tool_records_error():
    """LLM 调用了未注册的工具名 → 记录 error，循环继续。"""
    bus = EventBus()
    reg = _registry(_EchoTool())
    provider = _ScriptedProvider([
        ToolCallResponse(content="", tool_calls=[ToolCall(id="1", name="nonexistent", arguments={})]),
        ToolCallResponse(content="给不了", tool_calls=[]),
    ])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="q")
    state = await node.execute(state)

    assert len(state.tool_results) == 1
    assert "error" in state.tool_results[0]["result"]
    assert state.final_answer == "给不了"


@pytest.mark.asyncio
async def test_react_tool_execute_exception_recorded():
    """工具 execute 抛异常 → 记录 error，循环继续。"""

    class _BoomTool(Tool):
        name = "boom"
        description = "always fails"
        schema = ToolSchema(parameters=[])

        async def execute(self, **kwargs):
            raise RuntimeError("boom")

    bus = EventBus()
    reg = _registry(_BoomTool())
    provider = _ScriptedProvider([
        ToolCallResponse(content="", tool_calls=[ToolCall(id="1", name="boom", arguments={})]),
        ToolCallResponse(content="降级回答", tool_calls=[]),
    ])
    node = ToolNode(llm=provider, tool_registry=reg, event_bus=bus)

    state = AgentState(query="q")
    state = await node.execute(state)

    assert state.tool_results[0]["result"] == {"error": "boom"}
    assert state.final_answer == "降级回答"


@pytest.mark.asyncio
async def test_react_provider_no_tool_support_noop():
    """provider 不支持 chat_with_tools（NotImplementedError）→ 节点空过。"""

    class _NoToolsProvider(LLMProvider):
        async def generate(self, messages, **kwargs): return "ok"
        async def stream(self, messages, **kwargs): yield "ok"
        async def embed(self, texts, **kwargs): return [[0.0] for _ in texts]

    bus = EventBus()
    reg = _registry(_EchoTool())
    node = ToolNode(llm=_NoToolsProvider(), tool_registry=reg, event_bus=bus)

    state = AgentState(query="q")
    state = await node.execute(state)

    assert state.tool_results == []
    assert state.answered_by_tool is False
