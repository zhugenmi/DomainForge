"""模块 05 工具与 MCP：MCPToolAdapter 注册 + 敏感工具二次确认。

覆盖计划 §4 验证矩阵：
- test_mcp_adapter_register / test_mcp_adapter_execute_calls_client / test_mcp_skip_when_url_unset
- test_sensitive_tool_emits_confirm_event / test_sensitive_tool_resumes_after_confirm
- test_sensitive_tool_timeout_skips / test_chat_rejects_sensitive_non_stream
"""
import pytest

from app.llm.base import LLMProvider, ToolCall, ToolCallResponse
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.tool_node import ToolNode
from app.runtime.state.agent_state import AgentState
from app.tools.base import Tool
from app.tools.mcp.adapter import MCPToolAdapter, register_mcp_tools
from app.tools.mcp.client import MCPClient, MCPTool
from app.tools.registry.registry import ToolRegistry
from app.tools.registry.schema import ToolParameter, ToolSchema


# ---------- 3.1 MCPToolAdapter ----------


class _StubMCPClient:
    """绕过真实 HTTP 的 MCPClient stub。"""

    def __init__(self, server_url: str | None, tools: list[MCPTool], calls_log: list | None = None):
        self.server_url = server_url
        self.timeout = 5.0
        self._tools = tools
        self.calls_log = calls_log if calls_log is not None else []

    def available(self) -> bool:
        return bool(self.server_url)

    async def list_tools(self) -> list[MCPTool]:
        return list(self._tools)

    async def call_tool(self, name, arguments):
        self.calls_log.append((name, arguments))
        return {"ok": True, "name": name, "args": arguments}


@pytest.mark.asyncio
async def test_mcp_adapter_register():
    tools = [
        MCPTool(name="fs_read", description="read file", input_schema={
            "type": "object", "properties": {"path": {"type": "string", "description": "p"}}, "required": ["path"]
        }),
        MCPTool(name="fs_write", description="write file", input_schema={}),
    ]
    client = _StubMCPClient("http://mcp.local", tools)
    reg = ToolRegistry()
    n = await register_mcp_tools(reg, client)
    assert n == 2
    names = {t.name for t in reg.list_tools()}
    assert {"fs_read", "fs_write"} <= names
    # schema 映射：fs_read 有 path 参数
    fs_read = reg.get("fs_read")
    assert fs_read.permission_scope == "default"
    assert len(fs_read.schema.parameters) == 1
    assert fs_read.schema.parameters[0].name == "path"
    assert fs_read.schema.parameters[0].required is True


@pytest.mark.asyncio
async def test_mcp_adapter_execute_calls_client():
    mcp_tool = MCPTool(name="fs_read", description="read", input_schema={
        "type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]
    })
    calls_log: list = []
    client = _StubMCPClient("http://mcp.local", [mcp_tool], calls_log)
    adapter = MCPToolAdapter(client, mcp_tool)
    result = await adapter.execute(path="/tmp/x")
    assert calls_log == [("fs_read", {"path": "/tmp/x"})]
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_mcp_skip_when_url_unset():
    """MCP_SERVER_URL 未配置时不注册。"""
    client = _StubMCPClient(None, [MCPTool(name="x", description="", input_schema={})])
    reg = ToolRegistry()
    n = await register_mcp_tools(reg, client)
    assert n == 0
    assert reg.list_tools() == []


@pytest.mark.asyncio
async def test_mcp_register_list_failure_returns_zero():
    """list_tools 抛异常时不阻塞，返回 0。"""

    class _BoomClient(_StubMCPClient):
        async def list_tools(self):
            raise RuntimeError("network down")

    client = _BoomClient("http://mcp.local", [])
    reg = ToolRegistry()
    n = await register_mcp_tools(reg, client)
    assert n == 0


# ---------- 3.2 敏感工具二次确认 ----------


class _SensitiveTool(Tool):
    name = "sql_query"
    description = "execute sql"
    schema = ToolSchema(parameters=[ToolParameter(name="sql", type="string", required=True)])
    permission_scope = "sensitive"

    async def execute(self, **kwargs):
        return {"rows": [], "sql": kwargs.get("sql")}


class _ToolCapableProvider(LLMProvider):
    def __init__(self, tool_calls):
        self._tool_calls = list(tool_calls)

    async def generate(self, messages, **kwargs):
        return "ok"

    async def stream(self, messages, **kwargs):
        yield "ok"

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]

    async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
        # 真实 LLM 拿到工具结果后不再重复发起相同 tool_call；stub 首次返回后清空，
        # 模拟 ReAct 循环中 LLM 在工具执行后转入 finalize 的行为。
        calls = self._tool_calls
        self._tool_calls = []
        return ToolCallResponse(content="thinking", tool_calls=list(calls))


@pytest.mark.asyncio
async def test_sensitive_tool_emits_confirm_event():
    bus = EventBus()
    reg = ToolRegistry()
    reg.register(_SensitiveTool())
    calls = [ToolCall(id="1", name="sql_query", arguments={"sql": "DELETE FROM users"})]
    node = ToolNode(llm=_ToolCapableProvider(calls), tool_registry=reg, event_bus=bus)
    state = AgentState(query="del users")
    state.intent = "tool"

    state = await node.execute(state)
    # 排空事件队列，找确认事件
    events = []
    while not bus._queue.empty():
        events.append(bus._queue.get_nowait())

    # 不执行：tool_results 为空
    assert state.tool_results == []
    # 暂挂
    assert len(state.pending_tool_calls) == 1
    assert state.pending_tool_calls[0].name == "sql_query"
    # 发了确认事件
    import json as _json

    confirm_payloads = [
        _json.loads(e)["event"] for e in events if e and isinstance(e, str)
    ]
    assert "tool_confirm_required" in confirm_payloads
    confirm = [
        _json.loads(e) for e in events
        if e and isinstance(e, str) and _json.loads(e)["event"] == "tool_confirm_required"
    ][0]
    assert confirm["data"]["tool"] == "sql_query"
    assert confirm["data"]["args"] == {"sql": "DELETE FROM users"}


@pytest.mark.asyncio
async def test_sensitive_tool_resumes_after_confirm():
    """已确认的工具名在 confirmed_tool_names 中时，正常执行。"""
    bus = EventBus()
    reg = ToolRegistry()
    reg.register(_SensitiveTool())
    calls = [ToolCall(id="1", name="sql_query", arguments={"sql": "SELECT 1"})]
    node = ToolNode(llm=_ToolCapableProvider(calls), tool_registry=reg, event_bus=bus)
    state = AgentState(query="sel")
    state.intent = "tool"
    state.confirmed_tool_names = {"sql_query"}

    state = await node.execute(state)
    assert len(state.tool_results) == 1
    assert state.tool_results[0]["tool"] == "sql_query"
    assert state.pending_tool_calls == []


@pytest.mark.asyncio
async def test_sensitive_tool_resumes_from_pending():
    """暂挂后再次进入 ToolNode（pending 已设），确认后恢复执行。"""
    bus = EventBus()
    reg = ToolRegistry()
    reg.register(_SensitiveTool())
    node = ToolNode(llm=_ToolCapableProvider([]), tool_registry=reg, event_bus=bus)

    state = AgentState(query="sel")
    state.intent = "tool"
    state.pending_tool_calls = [ToolCall(id="1", name="sql_query", arguments={"sql": "SELECT 1"})]
    state.confirmed_tool_names = {"sql_query"}

    state = await node.execute(state)
    assert len(state.tool_results) == 1
    assert state.pending_tool_calls == []


@pytest.mark.asyncio
async def test_sensitive_tool_timeout_skips(monkeypatch):
    """pending_since 超过 SENSITIVE_TOOL_CONFIRM_TIMEOUT 时，暂挂调用标 skipped。"""
    from app.configs.settings import settings

    monkeypatch.setattr(settings, "SENSITIVE_TOOL_CONFIRM_TIMEOUT", 1)
    bus = EventBus()
    reg = ToolRegistry()
    reg.register(_SensitiveTool())
    node = ToolNode(llm=_ToolCapableProvider([]), tool_registry=reg, event_bus=bus)

    state = AgentState(query="sel")
    state.intent = "tool"
    state.pending_tool_calls = [ToolCall(id="1", name="sql_query", arguments={"sql": "SELECT 1"})]
    # 模拟 60s 前暂挂
    import time as _time

    state.pending_since = _time.time() - 100

    state = await node.execute(state)
    assert state.tool_results == [{"tool": "sql_query", "result": {"skipped": True, "reason": "confirm_timeout"}}]
    assert state.pending_tool_calls == []
