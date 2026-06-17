from contextlib import asynccontextmanager

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, audit, chat, evals, health, knowledge, sessions
from app.configs.settings import settings
from app.observability.logging.logger import setup_logging
from app.security.auth import router as auth_router
from app.services.preview_store import run_periodic_sweep


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    sweep_task = asyncio.create_task(run_periodic_sweep(interval=60))
    yield
    sweep_task.cancel()


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

# CORS：允许前端 dev origin 访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(evals.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
