from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMProvider
from app.memory.short_term.buffer_memory import BufferMemory
from app.observability.logging.logger import get_logger
from app.database.repositories.memory_repo import MemoryRepo

logger = get_logger("memory.summary")

SUMMARY_PROMPT = """请把以下对话压缩为不超过 200 字的摘要，保留关键事实、用户偏好与未解决的问题。

对话：
{dialog}"""


class SummaryMemory:
    """超过阈值轮数时，对会话历史生成摘要并写入 memories 表。"""

    def __init__(
        self,
        db: AsyncSession,
        llm: LLMProvider,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        threshold: int = 10,
        repo: MemoryRepo | None = None,
    ):
        self.db = db
        self.llm = llm
        self.session_id = session_id
        self.user_id = user_id
        self.threshold = threshold
        self.repo = repo or MemoryRepo(db)
        self.buffer = BufferMemory(db=db, session_id=session_id, max_messages=threshold * 2)

    async def maybe_summarize(self) -> str | None:
        messages = await self.buffer.get_messages()
        if len(messages) < self.threshold:
            return None
        dialog = "\n".join(f"[{m.role}]: {m.content}" for m in messages)
        try:
            summary = await self.llm.generate(
                messages=[{"role": "user", "content": SUMMARY_PROMPT.format(dialog=dialog)}],
                temperature=0.0,
                max_tokens=300,
            )
        except Exception as e:
            logger.warning("summary_llm_failed", error=str(e))
            return None
        await self.repo.create(
            user_id=self.user_id,
            memory_type="summary",
            content=summary,
            session_id=self.session_id,
            metadata={"message_count": len(messages)},
        )
        return summary

    async def load_summaries(self, limit: int = 3) -> list[str]:
        mems = await self.repo.list_by_session(self.session_id, memory_type="summary")
        return [m.content for m in mems[:limit]]


__all__ = ["SummaryMemory", "SUMMARY_PROMPT"]
