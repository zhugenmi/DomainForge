from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.message_repo import MessageRepo
from app.database.repositories.session_repo import SessionRepo
from app.database.repositories.user_repo import UserRepo
from app.database.session import get_db
from app.llm.embedding.embedding_service import EmbeddingService
from app.llm.router.model_router import ModelRouter
from app.observability.audit.audit_service import AuditService
from app.observability.tracing.tracer import request_trace
from app.memory.memory_service import MemoryService
from app.rag.retrieval.vector import VectorRetriever
from app.rag.service import RAGService
from app.runtime.runtime import AgentRuntime
from app.runtime.state.agent_state import AgentState
from app.schemas.chat import ChatRequest, ChatResponse
from app.security.prompt_guard import check_prompt
from app.tools.builtin.calculator_tool import CalculatorTool
from app.tools.builtin.file_tool import FileReadTool, FileWriteTool
from app.tools.builtin.knowledge_catalog_tool import ListKnowledgeBasesTool
from app.tools.builtin.knowledge_tool import KnowledgeTool
from app.tools.builtin.search_tool import SearchTool
from app.tools.registry.registry import registry as tool_registry
from app.services.cache import cache_get, cache_set

router = APIRouter(prefix="/chat", tags=["chat"])

_CHAT_CACHE_TTL = 600  # 10 分钟


async def _try_cache(session_id: uuid.UUID, query: str) -> dict | None:
    """命中缓存返回 {answer, intent}，否则 None。仅 intent=chat 的结果会被缓存。"""
    return await cache_get("chat", str(session_id), query)


async def _maybe_cache(session_id: uuid.UUID, query: str, intent: str, answer: str) -> None:
    if intent == "chat" and answer:
        await cache_set("chat", {"answer": answer, "intent": intent}, _CHAT_CACHE_TTL, str(session_id), query)


async def _ensure_default_user(db: AsyncSession):
    return await UserRepo(db).get_or_create_default()


async def _build_runtime(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> AgentRuntime:
    # 主链路接入 FallbackPolicy：主 provider 失败自动切备，无 secondary 时等价单 provider
    llm = ModelRouter().get_fallback()
    embedder = EmbeddingService(llm=llm)
    memory_service = MemoryService(
        db=db, llm=llm, session_id=session_id, user_id=user_id or uuid.UUID("00000000-0000-0000-0000-000000000001"), embedder=embedder
    )
    retriever = VectorRetriever(db=db, llm=llm)
    rag_service = RAGService(db=db, retriever=retriever, llm=llm, mode="hybrid")

    knowledge_tool = KnowledgeTool(rag_service=rag_service)
    catalog_tool = ListKnowledgeBasesTool(db=db)
    for tool in [knowledge_tool, catalog_tool, CalculatorTool(), SearchTool(), FileReadTool(), FileWriteTool()]:
        if tool_registry.get(tool.name) is None:
            tool_registry.register(tool)

    return AgentRuntime(
        llm=llm,
        memory_manager=memory_service,  # MemoryService 兼容 MemoryManager 接口
        rag_service=rag_service,
        tool_registry=tool_registry,
    )


async def _build_runtime_for_eval(db: AsyncSession):
    """为评测构造一个轻量 runtime（不持久化）。"""
    session_id = uuid.uuid4()
    return await _build_runtime(db, session_id)


def _guard(query: str) -> str | None:
    res = check_prompt(query)
    if res.blocked:
        return f"已拒绝处理疑似 Prompt 注入的输入：{res.reason}"
    return None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    blocked = _guard(request.query)
    if blocked:
        return ChatResponse(session_id=request.session_id or uuid.uuid4(), answer=blocked, intent="blocked")

    user = await _ensure_default_user(db)
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    audit = AuditService(db)

    if request.session_id is None:
        session = await session_repo.create(user_id=user.id, title=request.query[:50])
        request.session_id = session.id
    else:
        session = await session_repo.get(request.session_id)
        if session is None:
            session = await session_repo.create(user_id=user.id, title=request.query[:50])
            request.session_id = session.id

    await message_repo.create(session_id=request.session_id, role="user", content=request.query)

    # Prompt 缓存：命中且为 chat 意图时直接返回，跳过 Runtime
    cached = await _try_cache(request.session_id, request.query)
    if cached:
        answer = cached.get("answer", "")
        await message_repo.create(session_id=request.session_id, role="assistant", content=answer)
        await db.commit()
        return ChatResponse(
            session_id=request.session_id,
            answer=answer,
            intent=cached.get("intent", "chat"),
        )

    with request_trace("chat", session_id=str(request.session_id)) as span:
        await audit.log(span.trace_id, "chat_request", {"query": request.query, "session_id": str(request.session_id)})
        runtime = await _build_runtime(db, request.session_id, user_id=user.id)
        state = AgentState(query=request.query)
        state = await runtime.run(state)
        await audit.log(span.trace_id, "chat_response", {"intent": state.intent, "answer_len": len(state.final_answer)})

    # 非流式无法交互确认敏感工具：若有暂挂，拒绝并提示改用流式
    if state.pending_tool_calls:
        pending_names = sorted({tc.name for tc in state.pending_tool_calls})
        msg = f"敏感工具需流式确认，请改用 /chat/stream。待确认工具：{', '.join(pending_names)}"
        await message_repo.create(session_id=request.session_id, role="assistant", content=msg)
        await db.commit()
        return ChatResponse(session_id=request.session_id, answer=msg, intent="blocked")

    await _maybe_cache(request.session_id, request.query, state.intent, state.final_answer)
    await message_repo.create(session_id=request.session_id, role="assistant", content=state.final_answer)
    await db.commit()

    return ChatResponse(
        session_id=request.session_id,
        answer=state.final_answer,
        intent=state.intent,
    )


@router.get("/stream")
async def chat_stream(query: str, session_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    blocked = _guard(query)
    user = await _ensure_default_user(db)
    session_repo = SessionRepo(db)
    message_repo = MessageRepo(db)
    audit = AuditService(db)

    if session_id is None:
        session = await session_repo.create(user_id=user.id, title=query[:50])
        session_id = session.id
    else:
        session = await session_repo.get(session_id)
        if session is None:
            session = await session_repo.create(user_id=user.id, title=query[:50])
            session_id = session.id

    await message_repo.create(session_id=session_id, role="user", content=query)
    trace_id_holder: dict[str, str] = {}

    if blocked:
        async def _blocked_stream():
            payload = f'{{"event": "error", "data": {{"message": "{blocked}"}}}}'
            yield f"data: {payload}\n\n"
            await message_repo.create(session_id=session_id, role="assistant", content=blocked)
            await db.commit()

        return StreamingResponse(_blocked_stream(), media_type="text/event-stream")

    runtime = await _build_runtime(db, session_id, user_id=user.id)
    state = AgentState(query=query)

    # 流式场景的缓存命中：把缓存答案作为单个 final_answer 事件回放
    cached_stream = await _try_cache(session_id, query)

    async def _stream():
        if cached_stream:
            import json as _json

            payload = _json.dumps(
                {"event": "final_answer", "data": {"answer": cached_stream.get("answer", "")}},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
            await message_repo.create(session_id=session_id, role="assistant", content=cached_stream.get("answer", ""))
            await db.commit()
            return
        try:
            with request_trace("chat_stream", session_id=str(session_id)) as span:
                trace_id_holder["trace_id"] = span.trace_id
                await audit.log(span.trace_id, "chat_stream_request", {"query": query, "session_id": str(session_id)})
                async for chunk in runtime.run_stream(state):
                    yield chunk
        except Exception as e:
            import json as _json

            payload = _json.dumps({"event": "error", "data": {"message": str(e)}}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        finally:
            answer = state.final_answer or "[生成失败：未获得回复]"
            await _maybe_cache(session_id, query, state.intent, answer)
            await message_repo.create(session_id=session_id, role="assistant", content=answer)
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    return StreamingResponse(_stream(), media_type="text/event-stream")
