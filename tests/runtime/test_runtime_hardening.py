"""模块 03 Runtime 加固：chat_with_tools 抽象、Fallback 接入、Planner complexity、并行节点。"""
import asyncio
import time

import pytest

from app.llm.base import LLMProvider, ToolCall, ToolCallResponse
from app.llm.router.fallback import FallbackPolicy
from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.base import BaseNode
from app.runtime.nodes.intent_node import infer_complexity
from app.runtime.nodes.tool_node import ToolNode
from app.runtime.planner.planner import PlannerNode
from app.runtime.planner.task_decomposer import should_plan
from app.runtime.router.strategy import ConditionalStrategy
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry
from app.tools.registry.schema import ToolParameter, ToolSchema
from app.tools.base import Tool


# ---------- 3.1 chat_with_tools 抽象 ----------

class _ToolCapableProvider(LLMProvider):
    """模拟支持 function-calling 的 provider。"""

    def __init__(self, tool_calls: list[ToolCall] | None = None, raise_on_call: bool = False):
        self.model = "stub-tools"
        self._tool_calls = tool_calls or []
        self._raise = raise_on_call

    async def generate(self, messages, **kwargs):
        return "ok"

    async def stream(self, messages, **kwargs):
        yield "ok"

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]

    async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs):
        if self._raise:
            raise RuntimeError("provider down")
        return ToolCallResponse(content="thinking", tool_calls=list(self._tool_calls))


class _NoToolsProvider(LLMProvider):
    """不支持工具调用的 provider（如某些纯文本模型）。"""

    async def generate(self, messages, **kwargs):
        return "ok"

    async def stream(self, messages, **kwargs):
        yield "ok"

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]


@pytest.mark.asyncio
async def test_chat_with_tools_default_raises_not_implemented():
    p = _NoToolsProvider()
    with pytest.raises(NotImplementedError):
        await p.chat_with_tools([], [])


@pytest.mark.asyncio
async def test_openai_provider_tool_call_response_shape(monkeypatch):
    """验证 OpenAIProvider.chat_with_tools 把 OpenAI 响应转成 ToolCallResponse。"""
    from app.llm.providers.openai import OpenAIProvider

    class _FakeMsg:
        content = "let me check"
        tool_calls = [type("TC", (), {"id": "call_1", "function": type("F", (), {"name": "calc", "arguments": '{"x":1}'})()})()]

    class _FakeResp:
        choices = [type("C", (), {"message": _FakeMsg()})()]

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    return _FakeResp()

    prov = OpenAIProvider.__new__(OpenAIProvider)
    prov.client = _FakeClient()
    prov.model = "m"
    resp = await prov.chat_with_tools([{"role": "user", "content": "q"}], [])
    assert isinstance(resp, ToolCallResponse)
    assert resp.content == "let me check"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "calc"
    assert resp.tool_calls[0].arguments == {"x": 1}


# ---------- ToolNode 走抽象 ----------

class _EchoTool(Tool):
    name = "echo"
    description = "echo args back"
    schema = ToolSchema(parameters=[ToolParameter(name="msg", type="string", required=True)])
    permission_scope = "default"

    async def execute(self, **kwargs):
        return kwargs.get("msg")


@pytest.mark.asyncio
async def test_tool_node_uses_abstraction():
    bus = EventBus()
    reg = ToolRegistry()
    reg.register(_EchoTool())
    calls = [ToolCall(id="1", name="echo", arguments={"msg": "hi"})]
    node = ToolNode(llm=_ToolCapableProvider(tool_calls=calls), tool_registry=reg, event_bus=bus)
    state = AgentState(query="echo hi")
    state.intent = "tool"
    state = await node.execute(state)
    assert state.tool_results == [{"tool": "echo", "result": "hi"}]


@pytest.mark.asyncio
async def test_fallback_chat_with_tools_switches_provider():
    policy = FallbackPolicy(
        primary=_ToolCapableProvider(raise_on_call=True),
        secondary=_ToolCapableProvider(tool_calls=[ToolCall(id="1", name="echo", arguments={})]),
    )
    resp = await policy.chat_with_tools([], [])
    assert resp.tool_calls[0].name == "echo"


@pytest.mark.asyncio
async def test_fallback_chat_with_tools_skips_not_implemented():
    policy = FallbackPolicy(
        primary=_NoToolsProvider(),
        secondary=_ToolCapableProvider(tool_calls=[ToolCall(id="1", name="echo", arguments={})]),
    )
    resp = await policy.chat_with_tools([], [])
    assert resp.tool_calls[0].name == "echo"


@pytest.mark.asyncio
async def test_fallback_chat_with_tools_all_fail_raises():
    policy = FallbackPolicy(
        primary=_ToolCapableProvider(raise_on_call=True),
        secondary=_ToolCapableProvider(raise_on_call=True),
    )
    with pytest.raises(RuntimeError):
        await policy.chat_with_tools([], [])


@pytest.mark.asyncio
async def test_fallback_no_secondary_acts_as_single():
    """未配 secondary 时，FallbackPolicy 行为等价单 provider。"""
    policy = FallbackPolicy(primary=_ToolCapableProvider(tool_calls=[]))
    resp = await policy.chat_with_tools([], [])
    assert resp.tool_calls == []
    # generate 也正常
    out = await policy.generate([{"role": "user", "content": "hi"}])
    assert out == "ok"


# ---------- 3.3 Planner complexity ----------

def test_infer_complexity_levels():
    assert infer_complexity("你好") == "low"
    assert infer_complexity("请详细解释合同法第143条") == "medium"
    assert infer_complexity("请对比 A 和 B 两种方案的优劣") == "high"


def test_should_plan_uses_complexity():
    s = AgentState(query="请对比 A 和 B 两种方案")
    s.complexity = "high"
    assert should_plan(s)

    s2 = AgentState(query="你好")
    s2.complexity = "low"
    assert not should_plan(s2)


@pytest.mark.asyncio
async def test_planner_node_skips_low_complexity():
    bus = EventBus()
    node = PlannerNode(llm=_NoToolsProvider(), event_bus=bus)
    state = AgentState(query="你好")
    state.complexity = "low"
    state = await node.execute(state)
    assert state.plan == []


@pytest.mark.asyncio
async def test_planner_node_plans_high_complexity():
    class _PlanLLM(_NoToolsProvider):
        async def generate(self, messages, **kwargs):
            return '[{"step":"检索","action":"retrieve"}]'

    bus = EventBus()
    node = PlannerNode(llm=_PlanLLM(), event_bus=bus)
    state = AgentState(query="请对比 A 和 B 两种方案的优劣并总结")
    state.complexity = "high"
    state = await node.execute(state)
    assert len(state.plan) == 1


# ---------- 3.4 并行节点 ----------

class _DelayNode(BaseNode):
    """记录开始/结束时间戳，模拟耗时节点。"""

    def __init__(self, field_name: str, delay: float, intent_required: str | None = None):
        self.field_name = field_name
        self.delay = delay
        self.intent_required = intent_required
        self.started_at: float | None = None
        self.ended_at: float | None = None

    async def execute(self, state: AgentState) -> AgentState:
        self.started_at = time.monotonic()
        await asyncio.sleep(self.delay)
        self.ended_at = time.monotonic()
        setattr(state, self.field_name, [{"done": True}])
        return state


@pytest.mark.asyncio
async def test_parallel_retrieval_and_tool():
    retrieval = _DelayNode("retrieved_docs", 0.05)
    tool = _DelayNode("tool_results", 0.05)
    answer = _AnswerNode()
    intent = _SetIntentNode(intent="tool")  # tool 触发 tool 节点；plan 触发 retrieval

    nodes = {"intent": intent, "retrieval": retrieval, "tool": tool, "answer": answer}
    order = ["intent", "retrieval", "tool", "answer"]
    strategy = ConditionalStrategy(nodes, order)

    state = AgentState(query="q")
    state.plan = [{"step": "查知识", "action": "retrieve"}]
    state = await strategy.run(state)

    assert state.retrieved_docs == [{"done": True}]
    assert state.tool_results == [{"done": True}]
    # 两个节点应时间重叠（并行），总耗时 < 串行和 0.1s
    assert retrieval.ended_at is not None and tool.ended_at is not None
    overlap = min(retrieval.ended_at, tool.ended_at) - max(retrieval.started_at, tool.started_at)
    assert overlap >= 0, "retrieval 与 tool 应有时间重叠（并行执行）"


@pytest.mark.asyncio
async def test_serial_when_only_retrieval():
    retrieval = _DelayNode("retrieved_docs", 0.01)
    tool = _DelayNode("tool_results", 0.01)
    answer = _AnswerNode()
    intent = _SetIntentNode(intent="knowledge")

    nodes = {"intent": intent, "retrieval": retrieval, "tool": tool, "answer": answer}
    order = ["intent", "retrieval", "tool", "answer"]
    strategy = ConditionalStrategy(nodes, order)

    state = AgentState(query="q")
    state = await strategy.run(state)
    assert state.retrieved_docs == [{"done": True}]
    # intent=knowledge 且 plan 无 tool → tool 节点不执行
    assert tool.started_at is None


class _AnswerNode(BaseNode):
    async def execute(self, state: AgentState) -> AgentState:
        state.final_answer = "done"
        return state


class _SetIntentNode(BaseNode):
    def __init__(self, intent: str):
        self._intent = intent

    async def execute(self, state: AgentState) -> AgentState:
        state.intent = self._intent
        return state


# ---------- 3.2 Fallback 接入主链路（结构校验） ----------

def test_build_runtime_uses_fallback():
    """_build_runtime 应注入 FallbackPolicy 而非裸 provider。"""
    import inspect
    from app.api import chat as chat_mod

    src = inspect.getsource(chat_mod._build_runtime)
    # agent 注入后，fallback 构造移至 _llm_for_agent；二者之一出现即满足"走 FallbackPolicy"的意图
    assert "_llm_for_agent" in src
    assert inspect.getsource(chat_mod._llm_for_agent).count("get_fallback") >= 1
    assert "get_chat_llm" not in src


# ---------- 领域 agent 强制检索 ----------

@pytest.mark.asyncio
async def test_retrieval_forced_when_agent_domain_set():
    """agent_domain 非空时，即便 intent=chat 也应触发 retrieval 节点。

    回归：领域 agent 绑定后，意图分类为 chat 会导致 RetrievalNode 被跳过，
    进而 LLM 在无检索上下文时幻觉出 <knowledge_base_query> 标签而非作答。
    """
    retrieval = _DelayNode("retrieved_docs", 0.01)
    answer = _AnswerNode()
    intent = _SetIntentNode(intent="chat")  # 关键：意图为 chat

    nodes = {"intent": intent, "retrieval": retrieval, "tool": _DelayNode("tool_results", 0.01), "answer": answer}
    order = ["intent", "retrieval", "tool", "answer"]
    strategy = ConditionalStrategy(nodes, order)

    state = AgentState(query="宪法如何规定国徽")
    state.agent_domain = "legal"  # 领域 agent 注入
    state = await strategy.run(state)

    assert retrieval.started_at is not None, "agent_domain 非空时 retrieval 必须执行"
    assert state.retrieved_docs == [{"done": True}]


# ---------- Phase 10: 注册 web_search / reasoning 节点 ----------

@pytest.mark.asyncio
async def test_runtime_registers_web_search_and_reasoning_nodes():
    from app.runtime.runtime import AgentRuntime

    class _StubLLM:
        async def generate(self, messages, **kwargs):
            return "stub"

    rt = AgentRuntime(
        llm=_StubLLM(),
        memory_manager=None,
        rag_service=None,
        tool_registry=None,
    )
    bus = EventBus()
    router = rt._build_router(bus)
    names = [n.__class__.__name__.lower().replace("node", "") for n in router.nodes]
    assert "websearch" in names
    assert "reasoning" in names
    assert names.index("websearch") < names.index("tool")
    assert names.index("reasoning") < names.index("answer")
