from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.configs.settings import settings
from app.security.jwt import create_token, get_current_user
from app.security.permission import Role, require_role

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


_ADMIN_KEY = settings.ADMIN_API_KEY


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    # 极简身份：dev 环境任意用户名可登录；admin 角色由 ADMIN_API_KEY 校验
    role: Role = "user"
    if _ADMIN_KEY and req.password == _ADMIN_KEY:
        role = "admin"
    token = create_token(
        {
            "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, req.username)),
            "username": req.username,
            "role": role,
        }
    )
    return TokenResponse(access_token=token, role=role)


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.get("/admin-only")
async def admin_only(user=Depends(get_current_user), _: None = Depends(require_role("admin"))):
    return {"ok": True, "user": user}


__all__ = ["router", "LoginRequest", "TokenResponse"]
