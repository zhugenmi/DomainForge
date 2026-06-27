import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.agent import Agent


class AgentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> list[Agent]:
        result = await self.db.execute(
            select(Agent).order_by(Agent.is_builtin.desc(), Agent.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, agent_id: uuid.UUID) -> Agent | None:
        return await self.db.get(Agent, agent_id)

    async def get_by_name(self, name: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def create(self, **fields) -> Agent:
        agent = Agent(**fields)
        self.db.add(agent)
        await self.db.flush()
        return agent

    async def update(self, agent: Agent, fields: dict) -> Agent:
        for k, v in fields.items():
            setattr(agent, k, v)
        await self.db.flush()
        return agent

    async def delete(self, agent: Agent) -> None:
        await self.db.delete(agent)
        await self.db.flush()
