import uuid

import pytest

from app.database.models import Memory, Session, User
from app.database.repositories.memory_repo import MemoryRepo
from app.memory.long_term.vector_memory import VectorMemory
from app.memory.memory_service import MemoryService
from app.memory.summary.summary_memory import SummaryMemory


class _StubLLM:
    model = "stub"

    async def generate(self, messages, **kwargs):
        return "SUMMARY:" + messages[-1]["content"][:20]

    async def stream(self, messages, **kwargs):
        yield ""

    async def embed(self, texts, **kwargs):
        return [[float(len(t)), 0.0, 0.0] for t in texts]


@pytest.mark.asyncio
async def test_summary_memory_writes_when_threshold_met(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="u1", role="user"))
    await db.flush()
    session = Session(user_id=user_id, title="s")
    db.add(session)
    await db.flush()

    sm = SummaryMemory(db=db, llm=_StubLLM(), session_id=session.id, user_id=user_id, threshold=2)
    repo = MemoryRepo(db)
    # 直接造 2 条消息
    from app.database.models import Message

    db.add(Message(session_id=session.id, role="user", content="Q1"))
    db.add(Message(session_id=session.id, role="assistant", content="A1"))
    await db.flush()

    summary = await sm.maybe_summarize()
    assert summary is not None
    assert summary.startswith("SUMMARY:")
    summaries = await sm.load_summaries()
    assert len(summaries) == 1


@pytest.mark.asyncio
async def test_summary_memory_skips_when_below_threshold(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="u2", role="user"))
    await db.flush()
    session = Session(user_id=user_id, title="s")
    db.add(session)
    await db.flush()
    sm = SummaryMemory(db=db, llm=_StubLLM(), session_id=session.id, user_id=user_id, threshold=10)
    res = await sm.maybe_summarize()
    assert res is None


@pytest.mark.asyncio
async def test_vector_memory_remember_and_list(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="u3", role="user"))
    await db.flush()
    vm = VectorMemory(db=db, embedder=_StubEmbedder(), user_id=user_id)
    await vm.remember("用户偏好：喜欢简洁回答")
    all_mems = await vm.list_all()
    assert any("简洁" in m for m in all_mems)


class _StubEmbedder:
    async def embed(self, texts, **kwargs):
        return [[float(len(t)), 0.0, 0.0] for t in texts]

    async def embed_one(self, text):
        return [float(len(text)), 0.0, 0.0]


@pytest.mark.asyncio
async def test_memory_service_context_assembles_layers(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="u4", role="user"))
    await db.flush()
    session = Session(user_id=user_id, title="s")
    db.add(session)
    await db.flush()

    svc = MemoryService(db=db, llm=_StubLLM(), session_id=session.id, user_id=user_id)
    await svc.add_message("user", "你好")
    await svc.add_message("assistant", "您好")
    ctx = await svc.get_context(query="你好")
    roles = [c["role"] for c in ctx]
    assert "user" in roles
