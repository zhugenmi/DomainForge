from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Citation:
    index: int
    title: str
    locator: str
    snippet: str
    document_id: str
    chunk_id: str

    def render(self) -> str:
        return f"[{self.index}]"


def _locator(metadata: dict) -> str:
    article = metadata.get("article")
    if article:
        return str(article)
    idx = metadata.get("chunk_index")
    if idx is None:
        return "相关段落"
    return f"第{int(idx) + 1}段"


def make_citations(chunks: list[dict], max_snippet: int = 80) -> list[Citation]:
    out: list[Citation] = []
    for i, c in enumerate(chunks, start=1):
        metadata = c.get("metadata") or {}
        snippet = (c.get("content") or "").strip().replace("\n", " ")[:max_snippet]
        out.append(
            Citation(
                index=i,
                title=str(metadata.get("title") or metadata.get("source") or "未知文档"),
                locator=_locator(metadata),
                snippet=snippet,
                document_id=str(c.get("document_id") or ""),
                chunk_id=str(c.get("id") or ""),
            )
        )
    return out


def render_footnote(citations: list[Citation]) -> str:
    if not citations:
        return ""
    lines = ["引用："]
    for c in citations:
        lines.append(f"[{c.index}] {c.title} · {c.locator} | {c.snippet}")
    return "\n".join(lines)


__all__ = ["Citation", "make_citations", "render_footnote"]
