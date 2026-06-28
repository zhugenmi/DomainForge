import time
import uuid

import pytest

from app.services.attachment_store import AttachmentStore


@pytest.mark.asyncio
async def test_put_and_get():
    store = AttachmentStore(ttl=600)
    aid = await store.put("a.txt", "hello")
    got = await store.get(aid)
    assert got == {"filename": "a.txt", "content": "hello"}


@pytest.mark.asyncio
async def test_get_missing_returns_none():
    store = AttachmentStore(ttl=600)
    got = await store.get(uuid.uuid4())
    assert got is None


@pytest.mark.asyncio
async def test_pop_many_removes_and_returns():
    store = AttachmentStore(ttl=600)
    id1 = await store.put("a.txt", "x")
    id2 = await store.put("b.txt", "y")
    results = await store.pop_many([id1, id2])
    assert len(results) == 2
    filenames = {r["filename"] for r in results}
    assert filenames == {"a.txt", "b.txt"}
    again = await store.pop_many([id1, id2])
    assert again == []


@pytest.mark.asyncio
async def test_pop_many_skips_missing():
    store = AttachmentStore(ttl=600)
    id1 = await store.put("a.txt", "x")
    fake = uuid.uuid4()
    results = await store.pop_many([id1, fake])
    assert len(results) == 1
    assert results[0]["filename"] == "a.txt"


@pytest.mark.asyncio
async def test_ttl_expiry(monkeypatch):
    store = AttachmentStore(ttl=100)
    aid = await store.put("a.txt", "x")
    future = time.time() + 200
    monkeypatch.setattr("app.services.attachment_store.time.time", lambda: future)
    got = await store.get(aid)
    assert got is None


@pytest.mark.asyncio
async def test_sweep_removes_expired(monkeypatch):
    store = AttachmentStore(ttl=100)
    await store.put("a.txt", "x")
    future = time.time() + 200
    monkeypatch.setattr("app.services.attachment_store.time.time", lambda: future)
    removed = await store.sweep()
    assert removed == 1
