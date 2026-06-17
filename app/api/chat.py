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
from app.tools.builtin.knowledge_tool import KnowledgeTool
from app.tools.builtin.search_tool import SearchTool
from app.tools.registry.registry import registry as tool_registry

router = APIRouter(prefix="/chat", tags=["chat"])


async def _ensure_default_user(db: AsyncSession):
    return await UserRepo(db).get_or_create_default()


async def _build_runtime(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> AgentRuntime:
    llm = ModelRouter().get_chat_llm()
    embedder = EmbeddingService(llm=llm)
    memory_service = MemoryService(
        db=db, llm=llm, session_id=session_id, user_id=user_id or uuid.UUID("00000000-0000-0000-0000-000000000001"), embedder=embedder
    )
    retriever = VectorRetriever(db=db, llm=llm)
    rag_service = RAGService(db=db, retriever=retriever, llm=llm, mode="hybrid")

    knowledge_tool = KnowledgeTool(rag_service=rag_service)
    for tool in [knowledge_tool, CalculatorTool(), SearchTool(), FileReadTool(), FileWriteTool()]:
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

    with request_trace("chat", session_id=str(request.session_id)) as span:
        await audit.log(span.trace_id, "chat_request", {"query": request.query, "session_id": str(request.session_id)})
        runtime = await _build_runtime(db, request.session_id, user_id=user.id)
        state = AgentState(query=request.query)
        state = await runtime.run(state)
        await audit.log(span.trace_id, "chat_response", {"intent": state.intent, "answer_len": len(state.final_answer)})

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

    async def _stream():
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
            await message_repo.create(session_id=session_id, role="assistant", content=answer)
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    return StreamingResponse(_stream(), media_type="text/event-stream")
