"""滑动窗口限流 ASGI middleware。

Redis 可用时用 ZSET 实现滑动窗口；不可用时放行（不阻塞业务）。
key = rl:{identifier}:{route_group}，ZADD 时间戳，ZREMRANGEBYSCORE 清过期，ZCARD 计数。

使用纯 ASGI middleware 而非 BaseHTTPMiddleware：后者会把响应体消费放进
独立 task，流式响应（StreamingResponse）结束时该 task 被取消，cancel 信号
会传播进端点的 finally 块，打断 db.commit() 并抛出 CancelledError（BaseException，
不被 except Exception 捕获），导致助手消息丢失。
"""
from __future__ import annotations

import json
import time

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


def _client_id(scope) -> str:
    # 优先用已认证用户（若有），否则用 IP
    user = scope.get("user")
    if user and user.get("sub"):
        return f"u:{user['sub']}"
    fwd = None
    for name, value in scope.get("headers", ()):
        if name == b"x-forwarded-for":
            fwd = value.decode("latin-1")
            break
    if fwd:
        return f"ip:{fwd.split(',')[0].strip()}"
    client = scope.get("client")
    return f"ip:{client[0] if client else 'unknown'}"


class RateLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        group = _match_group(scope["path"])
        if group is None:
            await self.app(scope, receive, send)
            return

        prefix, max_req, window = group
        r = await get_redis()
        if r is None:
            await self.app(scope, receive, send)
            return

        ident = _client_id(scope)
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
            await self.app(scope, receive, send)
            return

        if count > max_req:
            logger.info("rate_limited", ident=ident, group=prefix, count=count)
            payload = json.dumps({"detail": "请求过于频繁，请稍后再试"}, ensure_ascii=False).encode("utf-8")
            await send({"type": "http.response.start", "status": 429,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(payload)).encode()),
                                    (b"retry-after", str(window).encode())]})
            await send({"type": "http.response.body", "body": payload})
            return

        await self.app(scope, receive, send)


__all__ = ["RateLimitMiddleware"]
