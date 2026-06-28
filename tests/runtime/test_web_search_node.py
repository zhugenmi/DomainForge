import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.web_search_node import WebSearchNode
from app.runtime.state.agent_state import AgentState
from app.tools.builtin.search_tool import SearchTool
from app.tools.registry.registry import ToolRegistry


class _StubSearchTool(SearchTool):
    def __init__(self, return_value):
        super().__init__()
        self._return = return_value
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self._return


class _StubLLM:
    def __init__(self, response: str = "refined query"):
        self._response = response
        self.calls = []

    async def generate(self, messages, **kwargs):
        self.calls.append(messages)
        return self._response


@pytest.mark.asyncio
async def test_web_search_forced():
    bus = EventBus()
    stub = _StubSearchTool([{"snippet": "result 1"}])
    registry = ToolRegistry()
    registry.register(stub)
    node = WebSearchNode(llm=_StubLLM("latest news"), tool_registry=registry, event_bus=bus)
    state = AgentState(query="latest news", web_search=True)

    await node.execute(state)

    assert len(stub.calls) == 1
    assert stub.calls[0]["query"] == "latest news"
    assert state.tool_results[0]["tool"] == "web_search"
    assert state.tool_results[0]["result"] == [{"snippet": "result 1"}]
    bus.done()
    events = [e async for e in bus.stream()]
    assert any("tool_called" in e for e in events)
    assert any("tool_result" in e for e in events)


@pytest.mark.asyncio
async def test_web_search_skipped_when_off():
    bus = EventBus()
    stub = _StubSearchTool([])
    registry = ToolRegistry()
    registry.register(stub)
    node = WebSearchNode(llm=_StubLLM(), tool_registry=registry, event_bus=bus)
    state = AgentState(query="hi", web_search=False)

    await node.execute(state)

    assert stub.calls == []
    assert state.tool_results == []
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_web_search_handles_tool_error():
    bus = EventBus()
    stub = _StubSearchTool([])

    async def _raise(**kwargs):
        raise RuntimeError("network down")

    stub.execute = _raise
    registry = ToolRegistry()
    registry.register(stub)
    node = WebSearchNode(llm=_StubLLM("x"), tool_registry=registry, event_bus=bus)
    state = AgentState(query="x", web_search=True)

    await node.execute(state)

    assert any(r["tool"] == "web_search" and "error" in r for r in state.tool_results)
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_web_search_refines_query_via_llm():
    """LLM 应把对话句提炼成搜索关键词，再调 SearchTool。"""
    bus = EventBus()
    stub = _StubSearchTool([{"snippet": "world cup"}])
    registry = ToolRegistry()
    registry.register(stub)
    llm = _StubLLM("2026世界杯 最新战况")
    node = WebSearchNode(llm=llm, tool_registry=registry, event_bus=bus)
    state = AgentState(query="请搜索当前世界杯的最新战况", web_search=True)

    await node.execute(state)

    # LLM 被调用一次做 query 提炼
    assert len(llm.calls) == 1
    # SearchTool 用提炼后的 query，不是原始对话句
    assert stub.calls[0]["query"] == "2026世界杯 最新战况"
    assert stub.calls[0]["query"] != "请搜索当前世界杯的最新战况"
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_web_search_falls_back_to_raw_query_if_llm_returns_empty():
    """LLM 返回空时回退到原始 query。"""
    bus = EventBus()
    stub = _StubSearchTool([{"snippet": "x"}])
    registry = ToolRegistry()
    registry.register(stub)
    llm = _StubLLM("   ")
    node = WebSearchNode(llm=llm, tool_registry=registry, event_bus=bus)
    state = AgentState(query="raw query", web_search=True)

    await node.execute(state)

    assert stub.calls[0]["query"] == "raw query"
    bus.done()
    _ = [e async for e in bus.stream()]
