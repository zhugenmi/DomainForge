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


def test_make_citations_semantic_fallback_when_no_article():
    """semantic chunk 无 article 且 content 无"第X条" → "相关段落"（不显示无意义的"第N段"）。"""
    cites = make_citations([_semantic_chunk()])
    assert cites[0].locator == "相关段落"
    assert cites[0].title == "合同法.txt"


def test_make_citations_semantic_extracts_article_from_content():
    """semantic chunk 无 article metadata，但 content 含"第X条" → 提取作为 locator。"""
    chunk = {
        "id": "c1",
        "content": "第五十条　宪法的修改，由全国人大常委会提议。",
        "document_id": "d1",
        "metadata": {"title": "宪法修正案.docx", "chunk_index": 33},
    }
    cites = make_citations([chunk])
    assert cites[0].locator == "第五十条"


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
    assert "相关段落" in out
    # 不再含调试用 doc=/chunk=
    assert "doc=" not in out
    assert "chunk=" not in out


def test_render_footnote_empty_returns_empty():
    assert render_footnote([]) == ""


# ---- reorder_citations: 按 answer 中 [N] 首次出现顺序重编号 ----


from app.rag.context.citation import reorder_citations  # noqa: E402


def _cite(idx: int, title: str = "t") -> dict:
    return {
        "index": idx,
        "title": title,
        "locator": "第X条",
        "snippet": "s",
        "document_id": "d",
        "chunk_id": f"c{idx}",
    }


def test_reorder_citations_renumbers_by_appearance_order():
    """answer 先引 [4] 再引 [1] 再引 [2] → 重编为 [1][2][3]，citations 按 4,1,2 顺序。"""
    answer = "国旗[4]。国歌[1]。义勇军[2]。"
    cites = [_cite(1), _cite(2), _cite(3), _cite(4), _cite(5)]
    new_answer, new_cites = reorder_citations(answer, cites)
    assert new_answer == "国旗[1]。国歌[2]。义勇军[3]。"
    assert [c["index"] for c in new_cites] == [1, 2, 3]
    # 原 [4] 现在是第 1 条
    assert new_cites[0]["chunk_id"] == "c4"
    assert new_cites[1]["chunk_id"] == "c1"
    assert new_cites[2]["chunk_id"] == "c2"


def test_reorder_citations_drops_unreferenced():
    """未被 answer 引用的 citation 过滤掉。"""
    answer = "只引了[2]。"
    cites = [_cite(1), _cite(2), _cite(3)]
    new_answer, new_cites = reorder_citations(answer, cites)
    assert new_answer == "只引了[1]。"
    assert len(new_cites) == 1
    assert new_cites[0]["chunk_id"] == "c2"
    assert new_cites[0]["index"] == 1


def test_reorder_citations_no_brackets_returns_empty():
    """answer 无任何 [N] → citations 清空，answer 原样返回。"""
    answer = "没有引用任何来源。"
    cites = [_cite(1), _cite(2)]
    new_answer, new_cites = reorder_citations(answer, cites)
    assert new_answer == answer
    assert new_cites == []


def test_reorder_citations_empty_citations_returns_unchanged():
    answer = "某回答[1]。"
    new_answer, new_cites = reorder_citations(answer, [])
    assert new_answer == answer
    assert new_cites == []


def test_reorder_citations_handles_repeated_bracket():
    """同一编号多次出现 → 只占一个序号，所有出现都重写。"""
    answer = "A[3] B[3] C[1]。"
    cites = [_cite(1), _cite(2), _cite(3)]
    new_answer, new_cites = reorder_citations(answer, cites)
    assert new_answer == "A[1] B[1] C[2]。"
    assert [c["chunk_id"] for c in new_cites] == ["c3", "c1"]


def test_reorder_citations_unknown_index_kept_as_is():
    """answer 引用了不存在的编号 → 该编号原样保留，不进入 citations。"""
    answer = "引[9]了。"
    cites = [_cite(1)]
    new_answer, new_cites = reorder_citations(answer, cites)
    assert new_answer == "引[9]了。"
    assert new_cites == []
