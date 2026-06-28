import pytest

from app.rag.chunk.finance_chunker import chunk_finance
from app.rag.chunk.legal_chunker import chunk_legal
from app.rag.chunk.semantic_chunker import chunk_semantic
from app.rag.context.builder import build_context
from app.rag.context.citation import make_citations, render_footnote
from app.rag.parser.html_parser import parse_html
from app.rag.parser.markdown_parser import parse_markdown
from app.rag.retrieval.bm25 import BM25Index, tokenize
from app.rag.retrieval.rrf import rrf_fuse


def test_parse_markdown_strips_syntax():
    out = parse_markdown("# 标题\n\n这是一段 **加粗** 文本 [链接](https://x.com)。")
    assert "标题" in out
    assert "**" not in out
    assert "[链接]" not in out
    assert "链接" in out


def test_parse_html_strips_tags():
    out = parse_html("<div><p>hello</p><script>bad()</script> world</div>")
    assert "hello" in out
    assert "bad" not in out
    assert "world" in out


def test_tokenize_cjk_by_char():
    tokens = tokenize("合同法 第三条")
    # jieba 未安装时走字切；安装后走词切。两种情况下都应产生非空 token
    assert len(tokens) > 0
    # 字切路径下验证单字；词切路径下验证词含 CJK 字符
    from app.rag.retrieval.bm25 import _JIEBA_AVAILABLE
    if not _JIEBA_AVAILABLE:
        assert "合" in tokens
        assert "条" in tokens
    else:
        assert any("合" in t for t in tokens)


def test_tokenize_handles_empty():
    assert tokenize("") == []
    assert tokenize(None) == []  # type: ignore[arg-type]


def test_semantic_chunker_basic():
    text = "段一内容。\n\n段二内容比较长。" * 5
    chunks = chunk_semantic(text, chunk_size=100, overlap=10)
    assert len(chunks) >= 1
    assert all(hasattr(c, "text") for c in chunks)


def test_legal_chunker_by_article():
    text = "第一条 立法目的。\n内容A。\n第二条 适用范围。\n内容B。"
    chunks = chunk_legal(text)
    assert len(chunks) == 2
    assert chunks[0].metadata["article"] == "第一条"
    assert chunks[1].metadata["article"] == "第二条"


def test_finance_chunker_by_heading():
    text = "1.1 产品说明\n详细内容。\n1.2 风险提示\n风险说明。"
    chunks = chunk_finance(text)
    assert len(chunks) >= 2


def test_rrf_fuse_combines_ranks():
    ranked = {"vector": ["b", "a", "c"], "bm25": ["b", "a", "d"]}
    fused = rrf_fuse(ranked, top_n=4)
    ids = [r.doc_id for r in fused]
    assert "a" in ids and "b" in ids
    # b 在两路都第一，应排第一
    assert fused[0].doc_id == "b"


def test_bm25_index_search():
    idx = BM25Index()
    idx.add("d1", "合同 法律 法条")
    idx.add("d2", "金融 产品 收益")
    res = idx.search("合同 法条", top_k=2)
    assert res[0][0] == "d1"


def test_build_context_with_citations():
    chunks = [
        {"id": "chunk-1", "content": "第一条内容", "document_id": "doc-1", "metadata": {"title": "doc-1", "chunk_index": 0}},
        {"id": "chunk-2", "content": "第二条内容", "document_id": "doc-1", "metadata": {"title": "doc-1", "chunk_index": 1}},
    ]
    ctx = build_context(chunks, memories=[{"role": "user", "content": "前问"}])
    assert "[1]" in ctx.text
    assert "第一条内容" in ctx.text
    assert len(ctx.citations) == 2
    assert "引用：" in ctx.text


def test_render_footnote_empty():
    assert render_footnote([]) == ""


@pytest.mark.asyncio
async def test_rag_service_bm25_mode(db):
    from app.database.repositories.document_repo import DocumentRepo
    from app.rag.service import RAGService

    repo = DocumentRepo(db)
    doc = await repo.create_document(domain="legal", title="t", source="s")
    await repo.create_chunk(document_id=doc.id, content="民法典 合同编", metadata={})
    await repo.create_chunk(document_id=doc.id, content="公司法 股东权利", metadata={})

    svc = RAGService(db=db, mode="bm25")
    results = await svc.search("合同", top_k=2)
    assert len(results) >= 1
    assert "合同" in results[0].content
