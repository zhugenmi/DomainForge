from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.document_repo import DocumentRepo
from app.llm.embedding.embedding_service import EmbeddingService
from app.observability.logging.logger import get_logger
from app.observability.metrics.metrics import metrics
from app.rag.chunk.finance_chunker import chunk_finance
from app.rag.chunk.legal_chunker import chunk_legal
from app.rag.chunk.semantic_chunker import Chunk, chunk_semantic
from app.rag.indexing.document_loader import load_document

logger = get_logger("rag.indexing")


@dataclass
class IndexResult:
    document_id: uuid.UUID
    chunk_count: int


class IndexingPipeline:
    def __init__(self, db: AsyncSession, embedder: EmbeddingService, repo: DocumentRepo | None = None):
        self.db = db
        self.embedder = embedder
        self.repo = repo or DocumentRepo(db)

    async def index_text(
        self,
        domain: str,
        title: str,
        content: str,
        source: str = "",
        chunk_strategy: str = "semantic",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> IndexResult:
        doc = await self.repo.create_document(domain=domain, title=title, source=source)
        meta = {"domain": domain, "title": title, "source": source}
        chunks = self._chunk(content, chunk_strategy, chunk_size, chunk_overlap, meta)
        if not chunks:
            return IndexResult(document_id=doc.id, chunk_count=0)

        embeddings = await self.embedder.embed([c.text for c in chunks])
        for c, emb in zip(chunks, embeddings):
            await self.repo.create_chunk(
                document_id=doc.id,
                content=c.text,
                embedding=emb,
                metadata=c.metadata,
            )
        metrics.inc("indexing.chunks", len(chunks))
        logger.info("document_indexed", document_id=str(doc.id), chunks=len(chunks), domain=domain)
        return IndexResult(document_id=doc.id, chunk_count=len(chunks))

    async def index_file(
        self,
        domain: str,
        path: str | Path,
        title: str | None = None,
        chunk_strategy: str = "semantic",
    ) -> IndexResult:
        p = Path(path)
        content = load_document(p)
        return await self.index_text(
            domain=domain,
            title=title or p.stem,
            content=content,
            source=str(p),
            chunk_strategy=chunk_strategy,
        )

    def _chunk(
        self,
        content: str,
        strategy: str,
        chunk_size: int,
        chunk_overlap: int,
        meta: dict,
    ) -> list[Chunk]:
        if strategy == "legal":
            return chunk_legal(content, metadata=meta)
        if strategy == "finance":
            return chunk_finance(content, metadata=meta)
        return chunk_semantic(content, chunk_size=chunk_size, overlap=chunk_overlap, metadata=meta)


__all__ = ["IndexingPipeline", "IndexResult"]
