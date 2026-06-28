"""检索分数不应污染 session 托管的 ORM 对象。

bug：BM25 fallback / hybrid rerank 把检索分数写到从 DB 查出的 DocumentChunk.score 列，
导致 chunk 变 dirty，后续 db.commit() 把临时分数持久化进 document_chunks.score。
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
import app.database.models  # noqa: F401
from app.database.models.chunk import DocumentChunk
from app.database.models.document import Document


async def _setup_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        doc = Document(domain="legal", title="t", source="s")
        db.add(doc)
        await db.flush()
        db.add(DocumentChunk(document_id=doc.id, content="劳动法规定工作时长每日八小时"))
        await db.commit()
    return engine, factory


@pytest.mark.asyncio
async def test_bm25_retrieval_does_not_dirty_chunks():
    from app.rag.retrieval.bm25 import BM25Retriever

    engine, factory = await _setup_db()
    try:
        async with factory() as db:
            retriever = BM25Retriever(db)
            results = await retriever.search("劳动法", top_k=5, domain="legal")
            assert len(results) > 0
            assert results[0].score is not None
            dirty = [o for o in db.dirty if isinstance(o, DocumentChunk)]
            assert dirty == [], f"检索污染了 session: {[(o.id, o.score) for o in dirty]}"
    finally:
        await engine.dispose()
