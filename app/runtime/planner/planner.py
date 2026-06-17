from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.planner.prompt import PLANNING_PROMPT
from app.runtime.planner.task_decomposer import needs_planning, parse_plan
from app.runtime.state.agent_state import AgentState


class PlannerNode(BaseNode):
    def __init__(self, llm: LLMProvider, event_bus: EventBus):
        self.llm = llm
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        if not needs_planning(state.query):
            state.plan = []
            return state
        prompt = PLANNING_PROMPT.format(query=state.query)
        raw = await self.llm.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        state.plan = parse_plan(raw)
        if state.plan:
            await self.event_bus.publish(
                SSEEventType.PLAN_GENERATED,
                {"steps": [s.get("step", "") for s in state.plan]},
            )
        return state
