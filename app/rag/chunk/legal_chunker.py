from __future__ import annotations

import re

from app.rag.chunk.semantic_chunker import Chunk

_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9]+条")
_CHAPTER_RE = re.compile(r"(?m)^[ \t　]*第[一二三四五六七八九十百千零〇0-9]+章[　\t ]*[^\n]*")


def chunk_legal(text: str, metadata: dict | None = None) -> list[Chunk]:
    """法律文本按"第X条"切分；向前追踪所属"第X章"（含章名）写入 metadata.chapter。

    无"第X条"时退化为段落切分。
    """
    base = metadata or {}
    article_matches = list(_ARTICLE_RE.finditer(text))
    if not article_matches:
        return [
            Chunk(p.strip(), {**base, "chunk_index": i})
            for i, p in enumerate(text.split("\n\n"))
            if p.strip()
        ]

    chapters = [(m.start(), m.group(0).strip()) for m in _CHAPTER_RE.finditer(text)]

    chunks: list[Chunk] = []
    for i, m in enumerate(article_matches):
        start = m.start()
        end = article_matches[i + 1].start() if i + 1 < len(article_matches) else len(text)
        block = text[start:end].strip()
        if not block:
            continue
        chapter = None
        for cpos, cval in chapters:
            if cpos >= start:
                break
            chapter = cval
        meta = {**base, "chunk_index": i, "article": m.group(0)}
        if chapter:
            meta["chapter"] = chapter
        chunks.append(Chunk(block, meta))
    return chunks


__all__ = ["chunk_legal"]
