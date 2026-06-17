from __future__ import annotations

from dataclasses import dataclass

from app.rag.context.citation import Citation, make_citations, render_footnote


@dataclass
class BuiltContext:
    text: str
    citations: list[Citation]


def build_context(
    chunks: list,
    memories: list[dict] | None = None,
    tool_results: list[dict] | None = None,
    max_chars: int = 4000,
) -> BuiltContext:
    """构造供 LLM 使用的上下文，附带引用编号。"""
    parts: list[str] = []
    citations = make_citations(chunks)

    if memories:
        hist = "\n".join(f"[{m['role']}]: {m['content']}" for m in memories)
        parts.append(f"对话历史：\n{hist}")

    if chunks:
        doc_lines = []
        for c, cite in zip(chunks, citations):
            doc_lines.append(f"{cite.render()} {c.content}")
        parts.append("检索到的知识：\n" + "\n---\n".join(doc_lines))

    if tool_results:
        tool_lines = [f"- {r.get('tool', '?')}: {r.get('result')}" for r in tool_results]
        parts.append("工具执行结果：\n" + "\n".join(tool_lines))

    text = "\n\n".join(parts) if parts else "无额外上下文"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...(上下文已截断)"
    if citations:
        text = text + "\n\n" + render_footnote(citations)
    return BuiltContext(text=text, citations=citations)


__all__ = ["build_context", "BuiltContext"]
