from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.memory_repo import MemoryRepo
from app.llm.base import LLMProvider
from app.llm.embedding.embedding_service import EmbeddingService
from app.memory.long_term.vector_memory import VectorMemory
from app.memory.manager import MemoryManager
from app.memory.short_term.buffer_memory import BufferMemory
from app.memory.summary.summary_memory import SummaryMemory


class MemoryService:
    """统一记忆入口：短期 + 摘要 + 长期。"""

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMProvider,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        embedder: EmbeddingService | None = None,
    ):
        self.db = db
        self.llm = llm
        self.session_id = session_id
        self.user_id = user_id
        self.embedder = embedder or EmbeddingService(llm=llm)
        self.short_term = BufferMemory(db=db, session_id=session_id)
        self.summary = SummaryMemory(db=db, llm=llm, session_id=session_id, user_id=user_id)
        self.long_term = VectorMemory(db=db, embedder=self.embedder, user_id=user_id)
        self.manager = MemoryManager(db=db, session_id=session_id)

    async def get_context(self, query: str | None = None) -> list[dict[str, str]]:
        """返回拼装好的上下文消息：摘要 + 长期 + 最近对话。"""
        ctx: list[dict[str, str]] = []
        summaries = await self.summary.load_summaries()
        for s in summaries:
            ctx.append({"role": "system", "content": f"会话摘要：{s}"})
        if query:
            try:
                long_term = await self.long_term.recall(query, top_k=3)
                for lt in long_term:
                    ctx.append({"role": "system", "content": f"长期记忆：{lt}"})
            except Exception:
                pass
        recent = await self.short_term.get_context()
        ctx.extend(recent)
        return ctx

    async def add_message(self, role: str, content: str) -> None:
        await self.short_term.add(role, content)

    async def persist_after_turn(self) -> None:
        await self.summary.maybe_summarize()


__all__ = ["MemoryService"]
