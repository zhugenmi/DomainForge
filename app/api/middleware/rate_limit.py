"""滑动窗口限流 middleware。

Redis 可用时用 ZSET 实现滑动窗口；不可用时放行（不阻塞业务）。
key = rl:{identifier}:{route_group}，ZADD 时间戳，ZREMRANGEBYSCORE 清过期，ZCARD 计数。
"""
from __future__ import annotations

import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.observability.logging.logger import get_logger
from app.services.redis import get_redis

logger = get_logger("rate_limit")

# 路由组配额：每 window 秒最多 max_req 次
_ROUTE_GROUPS: dict[str, tuple[int, int]] = {
    # prefix substring: (max_req, window_seconds)
    "/api/v1/chat": (20, 60),
    "/api/v1/knowledge/search": (60, 60),
}


def _match_group(path: str) -> tuple[str, int, int] | None:
    for prefix, (max_req, window) in _ROUTE_GROUPS.items():
        if path.startswith(prefix):
            return prefix, max_req, window
    return None


def _client_id(request: Request) -> str:
    # 优先用已认证用户（若有），否则用 IP
    user = getattr(request.state, "user", None)
    if user and user.get("sub"):
        return f"u:{user['sub']}"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        group = _match_group(request.url.path)
        if group is None:
            return await call_next(request)

        prefix, max_req, window = group
        r = await get_redis()
        if r is None:
            return await call_next(request)  # Redis 不可用，放行

        ident = _client_id(request)
        key = f"rl:{ident}:{prefix}"
        now = time.time()
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            _, _, count, _ = await pipe.execute()
        except Exception as e:
            logger.warning("rate_limit_check_failed", error=str(e))
            return await call_next(request)  # 限流检查失败，放行

        if count > max_req:
            logger.info("rate_limited", ident=ident, group=prefix, count=count)
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(window)},
            )
        return await call_next(request)


__all__ = ["RateLimitMiddleware"]
