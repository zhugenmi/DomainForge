import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.answer_node import AnswerNode
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry


class _CaptureLLM:
    """记录最后一次 generate 收到的 messages，返回固定字符串。"""

    def __init__(self):
        self.last_messages: list[dict] | None = None

    async def generate(self, messages, **kwargs):
        self.last_messages = messages
        return "ok"

    async def stream(self, messages, **kwargs):
        yield "ok"

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]


class _StubCatalogTool:
    name = "list_knowledge_bases"
    description = "列出知识库"
    schema = type("S", (), {"to_openai_function": lambda self: {}})()
    permission_scope = "read"
    timeout = 5.0

    def __init__(self, payload):
        self.payload = payload
        self.called = False

    async def execute(self, **kwargs):
        self.called = True
        return self.payload


class _OtherTool:
    name = "calculator"
    description = "四则运算"
    schema = type("S", (), {"to_openai_function": lambda self: {}})()
    permission_scope = "default"
    timeout = 30.0

    async def execute(self, **kwargs):
        return {}


@pytest.mark.asyncio
async def test_answer_node_injects_capability_context():
    llm = _CaptureLLM()
    bus = EventBus()
    catalog_tool = _StubCatalogTool(
        [
            {"name": "product", "is_builtin": True, "file_count": 3, "word_count": 500},
            {"name": "faq", "is_builtin": False, "file_count": 1, "word_count": 80},
        ]
    )
    registry = ToolRegistry()
    registry.register(catalog_tool)
    registry.register(_OtherTool())

    node = AnswerNode(llm=llm, event_bus=bus, tool_registry=registry)
    state = AgentState(query="当前有哪些知识库？")
    await node.execute(state)

    assert catalog_tool.called
    system_msg = llm.last_messages[0]["content"]
    assert "当前已配置的知识库" in system_msg
    assert "product（内置）" in system_msg
    assert "文档 3 篇" in system_msg
    assert "当前可用的工具/技能" in system_msg
    assert "calculator: 四则运算" in system_msg


@pytest.mark.asyncio
async def test_answer_node_without_registry_still_works():
    llm = _CaptureLLM()
    bus = EventBus()
    node = AnswerNode(llm=llm, event_bus=bus, tool_registry=None)
    state = AgentState(query="你好")
    await node.execute(state)

    assert state.final_answer == "ok"
    assert "无额外上下文" in llm.last_messages[0]["content"]


@pytest.mark.asyncio
async def test_answer_node_catalog_failure_is_degraded():
    llm = _CaptureLLM()
    bus = EventBus()

    class _Boom:
        name = "list_knowledge_bases"
        description = "x"
        schema = type("S", (), {"to_openai_function": lambda self: {}})()
        permission_scope = "read"
        timeout = 5.0

        async def execute(self, **kwargs):
            raise RuntimeError("db down")

    registry = ToolRegistry()
    registry.register(_Boom())

    node = AnswerNode(llm=llm, event_bus=bus, tool_registry=registry)
    state = AgentState(query="有哪些知识库")
    await node.execute(state)

    assert state.final_answer == "ok"
    system_msg = llm.last_messages[0]["content"]
    assert "当前可用的工具/技能" in system_msg
