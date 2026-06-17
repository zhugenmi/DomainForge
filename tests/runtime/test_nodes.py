import pytest
import pytest_asyncio

from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState


class MockNode(BaseNode):
    def __init__(self, field: str, value: str):
        self.field = field
        self.value = value

    async def execute(self, state: AgentState) -> AgentState:
        setattr(state, self.field, self.value)
        return state


@pytest.mark.asyncio
async def test_mock_node_execute():
    node = MockNode("intent", "chat")
    state = AgentState(query="你好")
    state = await node.execute(state)
    assert state.intent == "chat"


@pytest.mark.asyncio
async def test_event_bus_publish():
    bus = EventBus()
    await bus.publish(SSEEventType.INTENT_DETECTED, {"intent": "chat"})
    bus.done()

    events = []
    async for event in bus.stream():
        events.append(event)

    assert len(events) == 1
    assert "intent_detected" in events[0]
    assert "chat" in events[0]


@pytest.mark.asyncio
async def test_event_bus_error():
    bus = EventBus()
    await bus.publish_error("test error")
    bus.done()

    events = []
    async for event in bus.stream():
        events.append(event)

    assert len(events) == 1
    assert "error" in events[0]
