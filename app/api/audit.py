from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.observability.audit.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{trace_id}")
async def get_audit_trace(trace_id: str, db: AsyncSession = Depends(get_db)):
    service = AuditService(db)
    logs = await service.get_by_trace_id(trace_id)
    if not logs:
        raise HTTPException(status_code=404, detail="no audit logs for trace_id")
    return [
        {
            "id": str(log.id),
            "trace_id": log.trace_id,
            "action": log.action,
            "payload": log.payload,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("")
async def list_recent_audit(limit: int = 50, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.database.models.audit_log import AuditLog

    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [
        {
            "id": str(log.id),
            "trace_id": log.trace_id,
            "action": log.action,
            "payload": log.payload,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in result.scalars().all()
    ]
