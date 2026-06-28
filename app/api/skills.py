from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.configs.settings import settings
from app.database.session import async_session_factory
from app.skills.marketplace.local_adapter import LocalMarketplaceAdapter
from app.skills.registry import skill_registry
from app.skills.service import SkillService
from pathlib import Path

router = APIRouter(prefix="/skills", tags=["skills"])


def _marketplace_root() -> Path:
    return Path(settings.SKILLS_MARKETPLACE_ROOT)


async def get_skill_service() -> SkillService:
    """Production dependency: real DB + global registry + local marketplace."""
    db = async_session_factory()
    marketplace = LocalMarketplaceAdapter(_marketplace_root())
    return SkillService(
        db=db,
        registry=skill_registry,
        marketplace=marketplace,
        installed_root=Path(settings.SKILLS_INSTALLED_ROOT),
    )


class SetEnabledBody(BaseModel):
    enabled: bool


@router.get("/marketplace")
async def search_marketplace(q: str = ""):
    service = await get_skill_service()
    try:
        return [vars(p) for p in await service.search_marketplace(q)]
    finally:
        await service.db.close()


@router.get("/marketplace/{skill_id}")
async def get_marketplace_info(skill_id: str):
    service = await get_skill_service()
    try:
        info = await service.get_marketplace_info(skill_id)
        return vars(info)
    except KeyError:
        raise HTTPException(status_code=404, detail="skill not found in marketplace")
    finally:
        await service.db.close()


@router.post("/marketplace/{skill_id}/install")
async def install_skill(skill_id: str):
    service = await get_skill_service()
    try:
        dto = await service.install(skill_id)
        return vars(dto)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="skill not found in marketplace")
    finally:
        await service.db.close()


@router.get("/installed")
async def list_installed():
    service = await get_skill_service()
    try:
        return [vars(d) for d in await service.list_installed()]
    finally:
        await service.db.close()


@router.get("/installed/{name}")
async def get_installed(name: str):
    service = await get_skill_service()
    try:
        return vars(await service.get_installed(name))
    except KeyError:
        raise HTTPException(status_code=404, detail="skill not installed")
    finally:
        await service.db.close()


@router.patch("/installed/{name}")
async def set_enabled(name: str, body: SetEnabledBody):
    service = await get_skill_service()
    try:
        await service.set_enabled(name, body.enabled)
        rows = await service.list_installed()
        for r in rows:
            if r.name == name:
                return vars(r)
        raise HTTPException(status_code=404, detail="skill not installed")
    except KeyError:
        raise HTTPException(status_code=404, detail="skill not installed")
    finally:
        await service.db.close()


@router.delete("/installed/{name}")
async def uninstall_skill(name: str):
    service = await get_skill_service()
    try:
        await service.uninstall(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="skill not installed")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await service.db.close()
    from fastapi import Response
    return Response(status_code=204)
