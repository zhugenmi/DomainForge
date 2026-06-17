import pytest

from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.base import BaseNode
from app.runtime.planner.planner import PlannerNode
from app.runtime.planner.task_decomposer import needs_planning, parse_plan
from app.runtime.reflection.reflection_node import ReflectionNode
from app.runtime.reflection.retry_policy import RetryPolicy
from app.runtime.router.router import Router
from app.runtime.state.agent_state import AgentState


class StubLLM:
    model = "stub"

    def __init__(self, response: str):
        self.response = response

    async def generate(self, messages, **kwargs):
        return self.response

    async def stream(self, messages, **kwargs):
        yield self.response

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]


def test_needs_planning_heuristic():
    assert needs_planning("请对比 A 和 B 两种方案的优劣")
    assert not needs_planning("你好")


def test_parse_plan_extracts_array():
    raw = '一些解释\n[{"step":"检索","action":"retrieve"},{"step":"回答","action":"answer"}]'
    plan = parse_plan(raw)
    assert len(plan) == 2
    assert plan[0]["action"] == "retrieve"


def test_parse_plan_empty():
    assert parse_plan("[]") == []
    assert parse_plan("") == []


@pytest.mark.asyncio
async def test_planner_node_skips_simple_query():
    bus = EventBus()
    node = PlannerNode(llm=StubLLM('[]'), event_bus=bus)
    state = AgentState(query="你好")
    state = await node.execute(state)
    assert state.plan == []


@pytest.mark.asyncio
async def test_planner_node_parses_plan():
    bus = EventBus()
    node = PlannerNode(llm=StubLLM('[{"step":"检索","action":"retrieve"}]'), event_bus=bus)
    state = AgentState(query="请对比 A 和 B 两种方案的优劣并总结")
    state = await node.execute(state)
    assert len(state.plan) == 1


@pytest.mark.asyncio
async def test_reflection_marks_sufficient_when_no_answer():
    bus = EventBus()
    node = ReflectionNode(llm=StubLLM('{"sufficient":true}'), event_bus=bus)
    state = AgentState(query="q")
    state = await node.execute(state)
    assert state.retries == 0


@pytest.mark.asyncio
async def test_reflection_reroutes_on_insufficient():
    bus = EventBus()
    node = ReflectionNode(
        llm=StubLLM('{"sufficient":false,"next_action":"retrieve","reason":"need more"}'),
        event_bus=bus,
        retry_policy=RetryPolicy(max_retries=2),
    )
    state = AgentState(query="q")
    state.final_answer = "partial answer"
    state = await node.execute(state)
    assert state.retries == 1
    assert getattr(state, "_reflection_reroute", None) == "retrieval"


class _IntentNode(BaseNode):
    async def execute(self, state: AgentState) -> AgentState:
        state.intent = "chat"
        return state


class _AnswerNode(BaseNode):
    async def execute(self, state: AgentState) -> AgentState:
        state.final_answer = "ok"
        return state


@pytest.mark.asyncio
async def test_router_skips_unneeded_nodes():
    state = AgentState(query="hi")
    router = Router(nodes=[_IntentNode(), _AnswerNode()])
    state = await router.run(state)
    assert state.intent == "chat"
    assert state.final_answer == "ok"
