from __future__ import annotations

from app.memory.memory_service import MemoryService
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState


class MemoryNode(BaseNode):
    def __init__(self, memory_manager: MemoryService):
        self.memory_manager = memory_manager

    async def execute(self, state: AgentState) -> AgentState:
        state.memories = await self.memory_manager.get_context()
        return state
