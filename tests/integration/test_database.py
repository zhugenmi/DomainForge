import uuid

import pytest
import pytest_asyncio

from app.database.models import AuditLog, Document, DocumentChunk, Memory, Message, Session, User
from app.database.repositories.document_repo import DocumentRepo
from app.database.repositories.message_repo import MessageRepo
from app.database.repositories.session_repo import SessionRepo


@pytest.mark.asyncio
async def test_user_model(db):
    user = User(username="testuser", role="admin")
    db.add(user)
    await db.flush()
    assert user.id is not None
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_session_model(db):
    user_id = uuid.uuid4()
    user = User(id=user_id, username="testuser2", role="user")
    db.add(user)
    await db.flush()

    session = Session(user_id=user_id, title="Test Session")
    db.add(session)
    await db.flush()
    assert session.id is not None
    assert session.title == "Test Session"


@pytest.mark.asyncio
async def test_session_repo(db):
    user_id = uuid.uuid4()
    user = User(id=user_id, username="repouser", role="user")
    db.add(user)
    await db.flush()

    repo = SessionRepo(db)
    session = await repo.create(user_id=user_id, title="Repo Session")
    assert session.id is not None

    found = await repo.get(session.id)
    assert found is not None
    assert found.title == "Repo Session"


@pytest.mark.asyncio
async def test_message_repo(db):
    user_id = uuid.uuid4()
    user = User(id=user_id, username="msguser", role="user")
    db.add(user)
    await db.flush()

    session = Session(user_id=user_id, title="Msg Session")
    db.add(session)
    await db.flush()

    repo = MessageRepo(db)
    await repo.create(session_id=session.id, role="user", content="Hello")
    await repo.create(session_id=session.id, role="assistant", content="Hi there")

    messages = await repo.list_by_session(session.id)
    assert len(messages) == 2
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_document_repo(db):
    repo = DocumentRepo(db)
    doc = await repo.create_document(domain="legal", title="Test Doc", source="test.pdf")
    assert doc.id is not None

    chunk = await repo.create_chunk(document_id=doc.id, content="Test chunk content", metadata={"page": 1})
    assert chunk.id is not None
    assert chunk.content == "Test chunk content"


@pytest.mark.asyncio
async def test_audit_log(db):
    log = AuditLog(trace_id="trace-123", action="chat_request", payload={"query": "test"})
    db.add(log)
    await db.flush()
    assert log.id is not None
    assert log.trace_id == "trace-123"
