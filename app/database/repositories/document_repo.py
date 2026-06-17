import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.database.models.document import Document


class DocumentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(self, domain: str, title: str, source: str = "") -> Document:
        doc = Document(domain=domain, title=title, source=source)
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def create_chunk(
        self, document_id: uuid.UUID, content: str, embedding: list[float] | None = None, metadata: dict | None = None
    ) -> DocumentChunk:
        chunk = DocumentChunk(document_id=document_id, content=content, embedding=embedding, metadata_=metadata or {})
        self.db.add(chunk)
        await self.db.flush()
        return chunk

    async def vector_search(self, query_embedding: list[float], top_k: int = 5) -> list[DocumentChunk]:
        result = await self.db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(top_k)
        )
        return list(result.scalars().all())

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self.db.get(Document, document_id)

    async def list_by_domain(self, domain: str, limit: int = 100) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.domain == domain)
            .order_by(Document.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_stats_by_domain(self) -> list[dict]:
        """按 domain 聚合：file_count, word_count(sum), last_updated(max)。"""
        result = await self.db.execute(
            select(
                Document.domain.label("domain"),
                func.count(Document.id).label("file_count"),
                func.coalesce(func.sum(Document.word_count), 0).label("word_count"),
                func.max(Document.updated_at).label("last_updated"),
            )
            .group_by(Document.domain)
        )
        return [dict(r._mapping) for r in result.all()]

    async def update_document(self, doc_id: uuid.UUID, **kwargs) -> Document | None:
        doc = await self.get(doc_id)
        if doc is None:
            return None
        for k, v in kwargs.items():
            if hasattr(doc, k):
                setattr(doc, k, v)
        await self.db.flush()
        return doc

    async def delete_with_chunks(self, document_id: uuid.UUID) -> bool:
        doc = await self.get(document_id)
        if doc is None:
            return False
        await self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await self.db.delete(doc)
        await self.db.flush()
        return True
