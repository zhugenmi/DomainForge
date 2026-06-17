from __future__ import annotations

from abc import ABC, abstractmethod

from app.runtime.state.agent_state import AgentState


class BaseNode(ABC):
    @abstractmethod
    async def execute(self, state: AgentState) -> AgentState: ...
