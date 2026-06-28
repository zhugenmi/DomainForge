from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.agent import Agent
from app.database.models.message import Message
from app.database.models.session import Session
from app.database.repositories.session_repo import SessionRepo
from app.database.session import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    agent_id: uuid.UUID | None = None


class SessionUpdate(BaseModel):
    agent_id: uuid.UUID | None = None


def _serialize_session(s: Session) -> dict:
    return {
        "id": str(s.id),
        "user_id": str(s.user_id),
        "agent_id": str(s.agent_id) if s.agent_id else None,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("")
async def list_sessions(user_id: uuid.UUID | None = None, limit: int = 50, db: AsyncSession = Depends(get_db)):
    repo = SessionRepo(db)
    if user_id:
        sessions = await repo.list_by_user(user_id)
    else:
        result = await db.execute(select(Session).order_by(Session.created_at.desc()).limit(limit))
        sessions = list(result.scalars().all())
    return [_serialize_session(s) for s in sessions]


@router.post("")
async def create_session(req: SessionCreate, db: AsyncSession = Depends(get_db)):
    from app.database.repositories.user_repo import UserRepo

    user = await UserRepo(db).get_or_create_default()
    if req.agent_id is not None:
        agent = await db.get(Agent, req.agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")
    session = await SessionRepo(db).create(user_id=user.id, agent_id=req.agent_id)
    await db.commit()
    return _serialize_session(session)


@router.put("/{session_id}")
async def update_session(session_id: uuid.UUID, req: SessionUpdate, db: AsyncSession = Depends(get_db)):
    repo = SessionRepo(db)
    if req.agent_id is not None:
        agent = await db.get(Agent, req.agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="agent not found")
    session = await repo.update_agent_id(session_id, req.agent_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    await db.commit()
    return _serialize_session(session)


@router.get("/{session_id}")
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = SessionRepo(db)
    s = await repo.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    return _serialize_session(s)


@router.get("/{session_id}/messages")
async def list_messages(session_id: uuid.UUID, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    msgs = list(result.scalars().all())
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "citations": m.citations,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in msgs
    ]


@router.delete("/{session_id}")
async def delete_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = SessionRepo(db)
    s = await repo.get(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="session not found")
    # 级联清理：messages + memories(session 级) → session
    await db.execute(
        select(Message).where(Message.session_id == session_id)
    )
    msg_result = await db.execute(select(Message).where(Message.session_id == session_id))
    for m in msg_result.scalars().all():
        await db.delete(m)
    from app.database.models.memory import Memory

    mem_result = await db.execute(select(Memory).where(Memory.session_id == session_id))
    for mem in mem_result.scalars().all():
        await db.delete(mem)
    await db.delete(s)
    await db.commit()
    return {"deleted": str(session_id)}
