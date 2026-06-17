from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Citation:
    index: int
    document_id: str
    chunk_id: str
    snippet: str

    def render(self) -> str:
        return f"[{self.index}]"


_CITATION_RE = re.compile(r"\[(\d+)\]")


def make_citations(chunks: list, max_snippet: int = 80) -> list[Citation]:
    out: list[Citation] = []
    for i, c in enumerate(chunks, start=1):
        snippet = (c.content or "").strip().replace("\n", " ")[:max_snippet]
        out.append(
            Citation(
                index=i,
                document_id=str(c.document_id),
                chunk_id=str(c.id),
                snippet=snippet,
            )
        )
    return out


def render_footnote(citations: list[Citation]) -> str:
    if not citations:
        return ""
    lines = ["引用："]
    for c in citations:
        lines.append(f"[{c.index}] doc={c.document_id[:8]} chunk={c.chunk_id[:8]} | {c.snippet}")
    return "\n".join(lines)


__all__ = ["Citation", "make_citations", "render_footnote"]
