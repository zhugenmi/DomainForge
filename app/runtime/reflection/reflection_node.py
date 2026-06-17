from __future__ import annotations

from app.llm.base import LLMProvider
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.reflection.evaluator import evaluate_answer
from app.runtime.reflection.retry_policy import RetryPolicy
from app.runtime.state.agent_state import AgentState


class ReflectionNode(BaseNode):
    def __init__(self, llm: LLMProvider, event_bus: EventBus, retry_policy: RetryPolicy | None = None):
        self.llm = llm
        self.event_bus = event_bus
        self.retry_policy = retry_policy or RetryPolicy()

    async def execute(self, state: AgentState) -> AgentState:
        if not state.final_answer:
            return state
        has_context = bool(state.retrieved_docs or state.tool_results)
        verdict = await evaluate_answer(self.llm, state.query, state.final_answer, has_context)
        await self.event_bus.publish(SSEEventType.REFLECTION, verdict)
        next_action = verdict.get("next_action", "none")
        if verdict.get("sufficient") or not self.retry_policy.should_retry(state.retries):
            return state
        state.retries += 1
        if next_action == "retrieve":
            state._reflection_reroute = "retrieval"  # type: ignore[attr-defined]
        elif next_action == "tool":
            state._reflection_reroute = "tool"  # type: ignore[attr-defined]
        return state
