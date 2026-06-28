import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.answer_node import AnswerNode
from app.runtime.state.agent_state import AgentState


class _CaptureLLM:
    def __init__(self, response="ok"):
        self._response = response
        self.received_messages = None

    async def generate(self, messages, **kwargs):
        self.received_messages = messages
        return self._response

    async def stream(self, messages, **kwargs):
        yield self._response

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_answer_node_injects_reasoning():
    bus = EventBus()
    llm = _CaptureLLM("final answer")
    node = AnswerNode(llm=llm, event_bus=bus)
    state = AgentState(query="Q", deep_think=True)
    state.reasoning = "my deep thoughts"

    await node.execute(state)

    system_content = llm.received_messages[0]["content"]
    assert "my deep thoughts" in system_content
    assert state.final_answer == "final answer"
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_answer_node_injects_attachments():
    bus = EventBus()
    llm = _CaptureLLM("ans")
    node = AnswerNode(llm=llm, event_bus=bus)
    state = AgentState(query="Q")
    state.attachments = [{"filename": "a.txt", "content": "ATTACH BODY"}]

    await node.execute(state)

    system_content = llm.received_messages[0]["content"]
    assert "ATTACH BODY" in system_content
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_answer_node_no_injection_when_empty():
    bus = EventBus()
    llm = _CaptureLLM("ans")
    node = AnswerNode(llm=llm, event_bus=bus)
    state = AgentState(query="Q")

    await node.execute(state)

    system_content = llm.received_messages[0]["content"]
    assert "思考过程" not in system_content
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_answer_node_formats_search_results_readably():
    """web_search 结果应格式化为可读文本（title + snippet），不是 Python dict repr。"""
    bus = EventBus()
    llm = _CaptureLLM("ans")
    node = AnswerNode(llm=llm, event_bus=bus)
    state = AgentState(query="Q")
    state.tool_results = [
        {"tool": "web_search", "result": [
            {"title": "World Cup 2026", "url": "https://example.com", "snippet": "Latest scores"}
        ]}
    ]

    await node.execute(state)

    system_content = llm.received_messages[0]["content"]
    assert "World Cup 2026" in system_content
    assert "Latest scores" in system_content
    # 不应出现 Python dict repr
    assert "{'title'" not in system_content
    assert "{" not in system_content.split("工具执行结果")[1].split("\n")[1]
    bus.done()
    _ = [e async for e in bus.stream()]


@pytest.mark.asyncio
async def test_answer_node_warns_no_function_calls_when_web_search_used():
    """使用联网搜索后，应明确指示 LLM 不要输出函数调用标记。"""
    bus = EventBus()
    llm = _CaptureLLM("ans")
    node = AnswerNode(llm=llm, event_bus=bus)
    state = AgentState(query="Q")
    state.tool_results = [
        {"tool": "web_search", "result": [{"title": "t", "url": "u", "snippet": "s"}]}
    ]

    await node.execute(state)

    system_content = llm.received_messages[0]["content"]
    # 必须包含禁止输出函数调用标记的指令
    assert "function_calls" in system_content or "函数调用" in system_content
    bus.done()
    _ = [e async for e in bus.stream()]
