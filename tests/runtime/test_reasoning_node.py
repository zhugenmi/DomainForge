import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.reasoning_node import ReasoningNode
from app.runtime.state.agent_state import AgentState


class _StubLLM:
    def __init__(self, response: str):
        self._response = response
        self.calls = []

    async def generate(self, messages, **kwargs):
        self.calls.append(messages)
        return self._response


@pytest.mark.asyncio
async def test_reasoning_produces_chain():
    bus = EventBus()
    llm = _StubLLM("step1: analyze... step2: ...")
    node = ReasoningNode(llm=llm, event_bus=bus)
    state = AgentState(query="对比 A 和 B", deep_think=True)
    state.retrieved_docs = [{"content": "doc A info"}]
    state.tool_results = [{"tool": "calc", "result": 42}]
    state.attachments = [{"filename": "note.txt", "content": "extra"}]

    await node.execute(state)

    assert state.reasoning == "step1: analyze... step2: ..."
    assert len(llm.calls) == 1
    prompt_text = llm.calls[0][0]["content"]
    assert "对比 A 和 B" in prompt_text
    bus.done()
    events = [e async for e in bus.stream()]
    assert any("reflection" in e for e in events)


@pytest.mark.asyncio
async def test_reasoning_skipped_when_off():
    bus = EventBus()
    llm = _StubLLM("should not be called")
    node = ReasoningNode(llm=llm, event_bus=bus)
    state = AgentState(query="hi", deep_think=False)

    await node.execute(state)

    assert state.reasoning == ""
    assert llm.calls == []
    bus.done()
    _ = [e async for e in bus.stream()]
