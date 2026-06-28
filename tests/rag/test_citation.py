from __future__ import annotations

from app.rag.context.citation import Citation, make_citations, render_footnote


def _legal_chunk():
    return {
        "id": "chunk-aaa-11111111",
        "content": "第三条 民事主体的人身权利受法律保护。",
        "document_id": "doc-bbb-22222222",
        "metadata": {"title": "民法典.txt", "article": "第三条", "chunk_index": 2},
    }


def _semantic_chunk():
    return {
        "id": "chunk-ccc-33333333",
        "content": "合同是平等主体的自然人、法人、其他组织之间设立、变更、终止民事权利义务关系的协议。",
        "document_id": "doc-ddd-44444444",
        "metadata": {"title": "合同法.txt", "chunk_index": 4},
    }


def test_make_citations_legal_uses_article_as_locator():
    cites = make_citations([_legal_chunk()])
    assert len(cites) == 1
    c = cites[0]
    assert c.index == 1
    assert c.title == "民法典.txt"
    assert c.locator == "第三条"
    assert c.document_id == "doc-bbb-22222222"
    assert c.chunk_id == "chunk-aaa-11111111"
    assert "民事主体" in c.snippet


def test_make_citations_semantic_uses_chunk_index_as_locator():
    cites = make_citations([_semantic_chunk()])
    assert cites[0].locator == "第5段"  # chunk_index 4 + 1
    assert cites[0].title == "合同法.txt"


def test_make_citations_index_starts_at_1_and_increments():
    cites = make_citations([_legal_chunk(), _semantic_chunk()])
    assert [c.index for c in cites] == [1, 2]


def test_make_citations_snippet_truncated_to_80():
    long = "x" * 200
    chunk = {
        "id": "c1",
        "content": long,
        "document_id": "d1",
        "metadata": {"title": "t", "chunk_index": 0},
    }
    cites = make_citations([chunk])
    assert len(cites[0].snippet) == 80


def test_render_footnote_format():
    cites = make_citations([_legal_chunk(), _semantic_chunk()])
    out = render_footnote(cites)
    assert "[1]" in out
    assert "[2]" in out
    assert "民法典.txt" in out
    assert "第三条" in out
    assert "第5段" in out
    # 不再含调试用 doc=/chunk=
    assert "doc=" not in out
    assert "chunk=" not in out


def test_render_footnote_empty_returns_empty():
    assert render_footnote([]) == ""
