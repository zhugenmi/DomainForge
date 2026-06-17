from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.configs.settings import settings

ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def create_token(payload: dict[str, Any], expires_in: int = 86400) -> str:
    claims = {
        **payload,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}") from e


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    # dev 模式放行匿名调用，使用默认用户身份
    if creds is None:
        if settings.APP_ENV == "dev":
            return {"sub": "00000000-0000-0000-0000-000000000001", "username": "anonymous", "role": "admin"}
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    claims = decode_token(creds.credentials)
    return {"sub": claims.get("sub"), "username": claims.get("username", ""), "role": claims.get("role", "user")}
