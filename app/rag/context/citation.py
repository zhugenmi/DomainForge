from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Citation:
    index: int
    title: str
    chapter: str = ""
    locator: str = ""
    snippet: str = ""
    document_id: str = ""
    chunk_id: str = ""

    def render(self) -> str:
        return f"[{self.index}]"


_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9]+条")
_BRACKET_RE = re.compile(r"\[(\d+)\]")


def _locator(metadata: dict, content: str) -> str:
    """定位：优先 metadata.article；其次从 content 提取首个"第X条"；否则"相关段落"。
    不再使用无意义的"第N段"。"""
    article = metadata.get("article")
    if article:
        return str(article)
    m = _ARTICLE_RE.search(content or "")
    if m:
        return m.group(0)
    return "相关段落"


def make_citations(chunks: list[dict], max_snippet: int = 80) -> list[Citation]:
    out: list[Citation] = []
    for i, c in enumerate(chunks, start=1):
        metadata = c.get("metadata") or {}
        content = c.get("content") or ""
        snippet = content.strip().replace("\n", " ")[:max_snippet]
        out.append(
            Citation(
                index=i,
                title=str(metadata.get("title") or metadata.get("source") or "未知文档"),
                chapter=str(metadata.get("chapter") or ""),
                locator=_locator(metadata, content),
                snippet=snippet,
                document_id=str(c.get("document_id") or ""),
                chunk_id=str(c.get("id") or ""),
            )
        )
    return out


def reorder_citations(answer: str, citations: list[dict]) -> tuple[str, list[dict]]:
    """按 answer 中 [N] 首次出现顺序重编号 citations 为 1,2,3...
    未被 answer 引用的 citation 过滤掉。返回 (重写后的 answer, 重排后的 citations)。
    用于把 LLM 任意乱标的编号规整为正序，使正文 [N] 与参考列表一一对应。
    """
    if not citations:
        return answer, []
    cite_indices = {c["index"] for c in citations}
    seen_order: list[int] = []
    for m in _BRACKET_RE.finditer(answer):
        n = int(m.group(1))
        if n in cite_indices and n not in seen_order:
            seen_order.append(n)
    if not seen_order:
        return answer, []
    old_to_new = {old: new for new, old in enumerate(seen_order, start=1)}

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        return f"[{old_to_new[n]}]" if n in old_to_new else m.group(0)

    new_answer = _BRACKET_RE.sub(_replace, answer)
    cite_by_old = {c["index"]: c for c in citations}
    new_citations: list[dict] = []
    for new_idx, old in enumerate(seen_order, start=1):
        if old in cite_by_old:
            c = dict(cite_by_old[old])
            c["index"] = new_idx
            new_citations.append(c)
    return new_answer, new_citations


def render_footnote(citations: list[Citation]) -> str:
    if not citations:
        return ""
    lines = ["引用："]
    for c in citations:
        header = f"[{c.index}] {c.title}"
        if c.chapter:
            header += f" · {c.chapter}"
        if c.locator:
            header += f" · {c.locator}"
        lines.append(header)
        lines.append(c.snippet)
    return "\n".join(lines)


__all__ = ["Citation", "make_citations", "reorder_citations", "render_footnote"]
