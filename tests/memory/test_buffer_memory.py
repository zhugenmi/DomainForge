import uuid

import pytest
import pytest_asyncio

from app.database.models import Memory, Message, Session, User
from app.memory.manager import MemoryManager
from app.memory.short_term.buffer_memory import BufferMemory


@pytest.mark.asyncio
async def test_buffer_memory_add_and_get(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="memuser", role="user"))
    await db.flush()

    session = Session(user_id=user_id, title="Mem Session")
    db.add(session)
    await db.flush()

    memory = BufferMemory(db=db, session_id=session.id, max_messages=10)
    await memory.add("user", "Hello")
    await memory.add("assistant", "Hi")

    messages = await memory.get_messages()
    assert len(messages) == 2

    context = await memory.get_context()
    assert len(context) == 2
    roles = [c["role"] for c in context]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_memory_manager(db):
    user_id = uuid.uuid4()
    db.add(User(id=user_id, username="mgruser", role="user"))
    await db.flush()

    session = Session(user_id=user_id, title="Mgr Session")
    db.add(session)
    await db.flush()

    manager = MemoryManager(db=db, session_id=session.id)
    await manager.add_message("user", "Test question")
    await manager.add_message("assistant", "Test answer")

    context = await manager.get_context()
    assert len(context) == 2
