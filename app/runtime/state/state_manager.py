from __future__ import annotations

from app.runtime.state.agent_state import AgentState


class StateManager:
    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    def create(self, query: str) -> AgentState:
        state = AgentState(query=query)
        return state

    def update(self, state: AgentState, **kwargs) -> AgentState:
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state
