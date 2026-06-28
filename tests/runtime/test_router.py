import pytest

from app.runtime.nodes.base import BaseNode
from app.runtime.router.router import Router
from app.runtime.state.agent_state import AgentState


class SetIntentNode(BaseNode):
    async def execute(self, state: AgentState) -> AgentState:
        state.intent = "chat"
        return state


class SetAnswerNode(BaseNode):
    async def execute(self, state: AgentState) -> AgentState:
        state.final_answer = "Hello!"
        return state


@pytest.mark.asyncio
async def test_router_linear_execution():
    state = AgentState(query="hi")
    router = Router(nodes=[SetIntentNode(), SetAnswerNode()])
    state = await router.run(state)
    assert state.intent == "chat"
    assert state.final_answer == "Hello!"


class _FlagNode(BaseNode):
    """记录自己是否被执行。"""

    def __init__(self):
        self.executed = False

    async def execute(self, state: AgentState) -> AgentState:
        self.executed = True
        return state


class IntentNode(_FlagNode):
    pass


class WebSearchNode(_FlagNode):
    pass


class ReasoningNode(_FlagNode):
    pass


class AnswerNode(_FlagNode):
    pass


@pytest.mark.asyncio
async def test_router_skips_web_search_when_off():
    intent_n = IntentNode()
    ws_n = WebSearchNode()
    ans_n = AnswerNode()
    router = Router(nodes=[intent_n, ws_n, ans_n])
    state = AgentState(query="hi", web_search=False)
    await router.run(state)

    assert intent_n.executed is True
    assert ws_n.executed is False
    assert ans_n.executed is True


@pytest.mark.asyncio
async def test_router_runs_web_search_when_on():
    intent_n = IntentNode()
    ws_n = WebSearchNode()
    ans_n = AnswerNode()
    router = Router(nodes=[intent_n, ws_n, ans_n])
    state = AgentState(query="hi", web_search=True)
    await router.run(state)

    assert ws_n.executed is True


@pytest.mark.asyncio
async def test_router_skips_reasoning_when_off():
    r_n = ReasoningNode()
    ans_n = AnswerNode()
    router = Router(nodes=[r_n, ans_n])
    state = AgentState(query="hi", deep_think=False)
    await router.run(state)

    assert r_n.executed is False
    assert ans_n.executed is True


@pytest.mark.asyncio
async def test_router_runs_reasoning_when_on():
    r_n = ReasoningNode()
    ans_n = AnswerNode()
    router = Router(nodes=[r_n, ans_n])
    state = AgentState(query="hi", deep_think=True)
    await router.run(state)

    assert r_n.executed is True
