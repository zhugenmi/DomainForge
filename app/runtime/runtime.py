from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from app.llm.base import LLMProvider
from app.memory.memory_service import MemoryService
from app.rag.service import RAGService
from app.runtime.events.event_bus import EventBus
from app.runtime.nodes.answer_node import AnswerNode
from app.runtime.nodes.intent_node import IntentNode
from app.runtime.nodes.memory_node import MemoryNode
from app.runtime.nodes.reasoning_node import ReasoningNode
from app.runtime.nodes.retrieval_node import RetrievalNode
from app.runtime.nodes.tool_node import ToolNode
from app.runtime.nodes.web_search_node import WebSearchNode
from app.runtime.planner.planner import PlannerNode
from app.runtime.reflection.reflection_node import ReflectionNode
from app.runtime.router.router import Router
from app.runtime.state.agent_state import AgentState
from app.tools.registry.registry import ToolRegistry


class AgentRuntime:
    def __init__(
        self,
        llm: LLMProvider,
        memory_manager: MemoryService,
        rag_service: RAGService,
        tool_registry: ToolRegistry,
        max_iterations: int = 8,
        skill_registry=None,
    ):
        self.llm = llm
        self.memory_manager = memory_manager
        self.rag_service = rag_service
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations
        self.skill_registry = skill_registry

    def _build_router(self, event_bus: EventBus) -> Router:
        intent_node = IntentNode(llm=self.llm, event_bus=event_bus)
        planner_node = PlannerNode(llm=self.llm, event_bus=event_bus)
        memory_node = MemoryNode(memory_manager=self.memory_manager)
        retrieval_node = RetrievalNode(rag_service=self.rag_service, event_bus=event_bus)
        web_search_node = WebSearchNode(llm=self.llm, tool_registry=self.tool_registry, event_bus=event_bus)
        tool_node = ToolNode(llm=self.llm, tool_registry=self.tool_registry, event_bus=event_bus)
        reasoning_node = ReasoningNode(llm=self.llm, event_bus=event_bus)
        answer_node = AnswerNode(
            llm=self.llm,
            event_bus=event_bus,
            tool_registry=self.tool_registry,
            skill_registry=self.skill_registry,
        )
        reflection_node = ReflectionNode(llm=self.llm, event_bus=event_bus)
        return Router(
            nodes=[
                intent_node,
                planner_node,
                memory_node,
                retrieval_node,
                web_search_node,
                tool_node,
                reasoning_node,
                answer_node,
                reflection_node,
            ],
            max_iterations=self.max_iterations,
        )

    async def run(self, state: AgentState) -> AgentState:
        event_bus = EventBus()
        router = self._build_router(event_bus)
        state = await router.run(state)
        return state

    async def run_stream(self, state: AgentState) -> AsyncGenerator[str, None]:
        event_bus = EventBus()
        router = self._build_router(event_bus)

        async def _execute() -> None:
            try:
                await router.run(state)
            except Exception as e:
                await event_bus.publish_error(str(e))
            finally:
                event_bus.done()

        task = asyncio.create_task(_execute())
        async for chunk in event_bus.stream():
            yield chunk
        await task
