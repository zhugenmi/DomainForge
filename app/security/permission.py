from __future__ import annotations

from typing import Literal

from fastapi import Depends, HTTPException, status

from app.security.jwt import get_current_user

Role = Literal["admin", "operator", "user"]

_ROLE_RANK = {"user": 1, "operator": 2, "admin": 3}


def require_role(min_role: Role):
    """FastAPI dependency: 要求当前用户至少具备 min_role。"""

    async def _dep(user=Depends(get_current_user)) -> dict:
        rank = _ROLE_RANK.get(user.get("role", "user"), 0)
        if rank < _ROLE_RANK[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires role >= {min_role}",
            )
        return user

    return _dep


__all__ = ["require_role", "Role"]
