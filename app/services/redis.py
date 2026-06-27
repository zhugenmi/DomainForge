"""Redis 客户端单例，带优雅降级。

Redis 不可用时（未配置 / 连接失败），`get_redis()` 返回 None，
所有消费点应检查 None 并退化到无 Redis 行为（无缓存 / 无限流 / 进程内存储）。
"""
from __future__ import annotations

import redis.asyncio as redis

from app.configs.settings import settings
from app.observability.logging.logger import get_logger

logger = get_logger("redis")

_client: redis.Redis | None = None
_initialized: bool = False


async def _create_client() -> redis.Redis | None:
    if not settings.REDIS_ENABLED:
        logger.info("redis_disabled_by_config")
        return None
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        logger.info("redis_connected", url=settings.REDIS_URL)
        return client
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e), fallback="in-memory")
        return None


async def get_redis() -> redis.Redis | None:
    """懒初始化 Redis 客户端。不可用返回 None。"""
    global _client, _initialized
    if not _initialized:
        _client = await _create_client()
        _initialized = True
    return _client


async def close_redis() -> None:
    global _client, _initialized
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
    _client = None
    _initialized = False


def reset_redis_for_test() -> None:
    """测试用：重置单例状态。"""
    global _client, _initialized
    _client = None
    _initialized = False


__all__ = ["get_redis", "close_redis", "reset_redis_for_test"]
