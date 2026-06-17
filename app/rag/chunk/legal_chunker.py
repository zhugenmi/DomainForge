from __future__ import annotations

import re

from app.rag.chunk.semantic_chunker import Chunk, split_by_pattern

_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9]+条")


def chunk_legal(text: str, metadata: dict | None = None) -> list[Chunk]:
    """法律文本按"第X条"切分；保留条号作为元数据。"""
    return split_by_pattern(text, _ARTICLE_RE, "article", metadata)


__all__ = ["chunk_legal"]
