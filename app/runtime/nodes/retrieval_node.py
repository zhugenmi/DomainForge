from __future__ import annotations

from app.rag.service import RAGService
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState


class RetrievalNode(BaseNode):
    def __init__(self, rag_service: RAGService, event_bus: EventBus):
        self.rag_service = rag_service
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        if state.intent != "knowledge":
            return state
        await self.event_bus.publish(SSEEventType.RETRIEVAL_STARTED, {"query": state.query})
        chunks = await self.rag_service.search(state.query)
        state.retrieved_docs = [
            {
                "content": chunk.content,
                "document_id": str(chunk.document_id),
                "metadata": chunk.metadata_,
            }
            for chunk in chunks
        ]
        return state
