from __future__ import annotations

import re

from app.rag.chunk.semantic_chunker import Chunk, split_by_pattern

_HEADING_RE = re.compile(
    r"^(#{1,6}\s+.+$|第[一二三四五六七八九十]+[章节部分篇]|[0-9]+(?:\.[0-9]+)*\s+\S+)$",
    re.MULTILINE,
)


def chunk_finance(text: str, metadata: dict | None = None) -> list[Chunk]:
    """金融文本按标题层级切分。"""
    return split_by_pattern(text, _HEADING_RE, "heading", metadata)


__all__ = ["chunk_finance"]
