from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, agents, audit, chat, evals, health, knowledge, sessions, skills
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.configs.settings import settings
from app.database.repositories.skill_repo import SkillRepo
from app.database.session import async_session_factory
from app.observability.logging.logger import get_logger, setup_logging
from app.security.auth import router as auth_router
from app.services.preview_store import run_periodic_sweep
from app.services.redis import close_redis, get_redis
from app.skills.loader import load_skill_from_dir
from app.skills.registry import skill_registry
from app.tools.mcp.adapter import register_mcp_tools
from app.tools.mcp.client import MCPClient
from app.tools.registry.registry import registry as tool_registry

logger = get_logger("main")


def _check_secrets() -> None:
    """启动时检查关键密钥是否仍为默认/空值。dev 模式仅 warning，prod 模式已有 validator 兜底。"""
    for key in ("JWT_SECRET", "LLM_API_KEY"):
        if settings.is_secret_default(key):
            logger.warning("secret_default", key=key, env=settings.APP_ENV, msg=f"{key} 仍为默认/空值，生产前必须替换")


async def _register_mcp_tools() -> None:
    """启动时若配置 MCP_SERVER_URL，拉取远端工具注册到全局 registry。失败不阻塞。"""
    if not settings.MCP_SERVER_URL:
        return
    client = MCPClient(server_url=settings.MCP_SERVER_URL, timeout=settings.MCP_LIST_TIMEOUT)
    await register_mcp_tools(tool_registry, client)


async def _load_installed_skills() -> None:
    """启动时从 DB 重建 SkillRegistry：加载所有 enabled=True 的已安装 skill。失败不阻塞。"""
    try:
        async with async_session_factory() as db:
            rows = await SkillRepo(db).list_enabled()
    except Exception as e:
        logger.warning("skill_load_failed", error=str(e))
        return
    for row in rows:
        try:
            desc = load_skill_from_dir(Path(row.installed_path))
            skill_registry.add(desc)
        except Exception as e:
            logger.warning("skill_load_one_failed", name=row.name, error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _check_secrets()
    # 初始化 Redis（不可用则降级，不阻塞启动）
    await get_redis()
    # 拉取 MCP 远端工具（未配置或失败时跳过）
    await _register_mcp_tools()
    # 从 DB 重建已安装 skill registry
    await _load_installed_skills()
    sweep_task = asyncio.create_task(run_periodic_sweep(interval=60))
    yield
    # 优雅关机：取消后台清扫，关闭 Redis 连接
    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    await close_redis()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

# CORS：从配置读，默认仅允许前端 dev origin；生产通过 CORS_ORIGINS env 收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 限流：Redis 可用时按路由组滑动窗口限流，不可用放行
app.add_middleware(RateLimitMiddleware)

app.include_router(health.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "status": "ok",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
app.include_router(chat.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(evals.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(skills.router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
