from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.database.repositories.agent_repo import AgentRepo
from app.database.repositories.category_repo import CategoryRepo
from app.database.session import get_db
from app.schemas.agent import AgentCreate, AgentInfo, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


def _available_models() -> list[str]:
    raw = settings.AVAILABLE_MODELS.strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return [settings.DEFAULT_LLM_MODEL] if settings.DEFAULT_LLM_MODEL else []


@router.get("/models", response_model=list[str])
async def list_agent_models():
    """返回配置中可用的模型列表，供 agent 表单下拉。"""
    return _available_models()


async def _validate_domain(db: AsyncSession, domain: str | None) -> None:
    if domain is None:
        return
    cat = await CategoryRepo(db).get_by_name(domain.strip().lower())
    if cat is None:
        raise HTTPException(status_code=404, detail=f"category not found: {domain}")


@router.get("", response_model=list[AgentInfo])
async def list_agents(db: AsyncSession = Depends(get_db)):
    agents = await AgentRepo(db).list_all()
    return agents


@router.post("", response_model=AgentInfo, status_code=201)
async def create_agent(req: AgentCreate, db: AsyncSession = Depends(get_db)):
    await _validate_domain(db, req.domain)
    repo = AgentRepo(db)
    if await repo.get_by_name(req.name) is not None:
        raise HTTPException(status_code=409, detail=f"agent name exists: {req.name}")
    agent = await repo.create(
        name=req.name,
        description=req.description,
        system_prompt=req.system_prompt,
        model_name=req.model_name,
        temperature=req.temperature,
        domain=req.domain,
        is_builtin=False,
    )
    await db.commit()
    return agent


@router.get("/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await AgentRepo(db).get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentInfo)
async def update_agent(agent_id: uuid.UUID, req: AgentUpdate, db: AsyncSession = Depends(get_db)):
    repo = AgentRepo(db)
    agent = await repo.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    fields = req.model_dump(exclude_unset=True)
    if "is_builtin" in fields:
        raise HTTPException(status_code=422, detail="is_builtin cannot be changed")
    if "domain" in fields:
        await _validate_domain(db, fields["domain"])
    if "name" in fields and fields["name"] != agent.name:
        if await repo.get_by_name(fields["name"]) is not None:
            raise HTTPException(status_code=409, detail=f"agent name exists: {fields['name']}")
    await repo.update(agent, fields)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = AgentRepo(db)
    agent = await repo.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="agent not found")
    if agent.is_builtin:
        raise HTTPException(status_code=403, detail="builtin agent cannot be deleted")
    await repo.delete(agent)
    await db.commit()
    return None
