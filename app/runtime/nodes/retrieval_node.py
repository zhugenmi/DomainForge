from __future__ import annotations

from app.observability.logging.logger import get_logger
from app.rag.service import RAGService
from app.runtime.events.event_bus import EventBus
from app.runtime.events.event_type import SSEEventType
from app.runtime.nodes.base import BaseNode
from app.runtime.state.agent_state import AgentState

logger = get_logger("runtime.retrieval")


class RetrievalNode(BaseNode):
    def __init__(self, rag_service: RAGService, event_bus: EventBus):
        self.rag_service = rag_service
        self.event_bus = event_bus

    async def execute(self, state: AgentState) -> AgentState:
        # agent_domain 非空时强制检索（领域 agent 必须拿到领域知识上下文）
        if state.intent != "knowledge" and not state.agent_domain:
            return state
        await self.event_bus.publish(SSEEventType.RETRIEVAL_STARTED, {"query": state.query})
        try:
            chunks = await self.rag_service.search(state.query, domain=state.agent_domain)
        except Exception as e:
            # 检索后端不可用（如 pgvector 缺失、DB 方言不兼容）不应阻断主链路；
            # agent 仍可基于自身能力上下文作答。与 AnswerNode._build_capability_context 同构。
            logger.warning("retrieval_failed", error=str(e), domain=state.agent_domain)
            state.retrieved_docs = []
            return state
        state.retrieved_docs = [
            {
                "content": chunk.content,
                "document_id": str(chunk.document_id),
                "metadata": chunk.metadata_,
            }
            for chunk in chunks
        ]
        return state
