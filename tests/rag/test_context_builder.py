from __future__ import annotations

from app.rag.context.builder import build_context


def _chunks():
    return [
        {
            "id": "c1",
            "content": "第三条 内容A。",
            "document_id": "d1",
            "metadata": {"title": "民法典.txt", "article": "第三条"},
        },
        {
            "id": "c2",
            "content": "第四条 内容B。",
            "document_id": "d1",
            "metadata": {"title": "民法典.txt", "article": "第四条"},
        },
    ]


def test_build_context_numbers_chunks_with_brackets():
    ctx = build_context(_chunks())
    assert "[1]" in ctx.text
    assert "[2]" in ctx.text
    assert "第三条 内容A。" in ctx.text
    assert "第四条 内容B。" in ctx.text


def test_build_context_appends_footnote():
    ctx = build_context(_chunks())
    assert "引用：" in ctx.text
    assert "民法典.txt" in ctx.text


def test_build_context_returns_citations():
    ctx = build_context(_chunks())
    assert len(ctx.citations) == 2
    assert ctx.citations[0].index == 1
    assert ctx.citations[1].index == 2


def test_build_context_empty_chunks_no_footnote():
    ctx = build_context([])
    assert "引用：" not in ctx.text
    assert ctx.citations == []


def test_build_context_includes_memories():
    ctx = build_context([], memories=[{"role": "user", "content": "你好"}])
    assert "你好" in ctx.text
    assert "对话历史" in ctx.text
