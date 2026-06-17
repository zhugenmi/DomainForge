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
