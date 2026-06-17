from __future__ import annotations

from app.llm.embedding.embedding_service import EmbeddingService
from app.rag.chunk.semantic_chunker import Chunk


async def embed_chunks(chunks: list[Chunk], service: EmbeddingService) -> list[list[float]]:
    return await service.embed([c.text for c in chunks])


__all__ = ["embed_chunks"]
