from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.audit_log import AuditLog
from app.observability.logging.logger import get_logger

logger = get_logger("audit")


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(self, trace_id: str, action: str, payload: dict | None = None) -> AuditLog:
        entry = AuditLog(trace_id=trace_id, action=action, payload=payload or {})
        self.db.add(entry)
        await self.db.flush()
        logger.info("audit_log", trace_id=trace_id, action=action)
        return entry

    async def get_by_trace_id(self, trace_id: str) -> list[AuditLog]:
        from sqlalchemy import select

        result = await self.db.execute(select(AuditLog).where(AuditLog.trace_id == trace_id))
        return list(result.scalars().all())
