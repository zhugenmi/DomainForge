from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.settings import settings
from app.database.repositories.user_repo import UserRepo
from app.database.session import get_db
from app.observability.audit.audit_service import AuditService
from app.observability.logging.logger import get_logger
from app.observability.tracing.tracer import request_trace
from app.security.jwt import create_token, get_current_user
from app.security.password import verify_password
from app.security.permission import Role, require_role

logger = get_logger("auth")
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str = ""
    # admin 升级：dev/prod 一致，由 ADMIN_API_KEY 决定
    admin_key: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _resolve_role(req: LoginRequest) -> Role:
    """admin 角色统一由 ADMIN_API_KEY 决定，与 dev/prod 无关。"""
    if settings.ADMIN_API_KEY and req.admin_key == settings.ADMIN_API_KEY:
        return "admin"
    return "user"


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")

    if settings.APP_ENV == "dev":
        # dev：任意 username 可登录，便于本地联调
        role: Role = _resolve_role(req)
        user_sub = str(uuid.uuid5(uuid.NAMESPACE_DNS, req.username))
        username = req.username
    else:
        # prod：必须校验密码
        if not req.password:
            await _audit_login(db, username=req.username, ip=ip, ua=ua, ok=False, reason="missing_password")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="生产环境登录需要密码")
        repo = UserRepo(db)
        user = await repo.get_by_username(req.username)
        if user is None or not user.password_hash or not verify_password(req.password, user.password_hash):
            await _audit_login(db, username=req.username, ip=ip, ua=ua, ok=False, reason="bad_credentials")
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        role = _resolve_role(req)
        user_sub = str(user.id)
        username = user.username

    token = create_token({"sub": user_sub, "username": username, "role": role})
    await _audit_login(db, username=username, ip=ip, ua=ua, ok=True, role=role)
    await db.commit()
    return TokenResponse(access_token=token, role=role)


@router.post("/logout")
async def logout(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    with request_trace("auth.logout") as span:
        await AuditService(db).log(span.trace_id, "logout", {"username": user.get("username", "")})
    await db.commit()
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user


@router.get("/admin-only")
async def admin_only(user=Depends(get_current_user), _: None = Depends(require_role("admin"))):
    return {"ok": True, "user": user}


async def _audit_login(
    db: AsyncSession,
    *,
    username: str,
    ip: str,
    ua: str,
    ok: bool,
    role: str | None = None,
    reason: str | None = None,
) -> None:
    with request_trace("auth.login") as span:
        action = "login_success" if ok else "login_failed"
        payload: dict = {"username": username, "ip": ip, "user_agent": ua}
        if role:
            payload["role"] = role
        if reason:
            payload["reason"] = reason
        await AuditService(db).log(span.trace_id, action, payload)
    logger.info("auth_login", username=username, ok=ok, ip=ip)


__all__ = ["router", "LoginRequest", "TokenResponse"]
