"""模块 01 RAG 增强：真实 Rerank、jieba、Query 改写、domain 过滤。"""
import json

import pytest

from app.llm.base import LLMProvider
from app.llm.rerank.bge_reranker import BGEReranker, RerankCandidate
from app.llm.rerank.rerank_service import RerankService
from app.rag.retrieval.query_rewriter import QueryRewriter, _should_rewrite


# ---------- 3.1 真实 Rerank ----------

class _FakeRerankResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_bge_reranker_real_api_results_format(monkeypatch):
    reranker = BGEReranker(api_key="k", base_url="http://rerank")
    assert reranker.available()

    captured = {}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeRerankResponse({"results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.5}]})

    monkeypatch.setattr("app.llm.rerank.bge_reranker.httpx.AsyncClient", _FakeClient)
    out = await reranker.rerank("q", ["d0", "d1", "d2"], top_n=2)
    assert len(out) == 2
    assert out[0].text == "d1"  # index 1, score 0.9 排前
    assert out[0].score == 0.9
    assert captured["json"]["query"] == "q"


@pytest.mark.asyncio
async def test_bge_reranker_scores_format(monkeypatch):
    reranker = BGEReranker(api_key="k", base_url="http://rerank")

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            return _FakeRerankResponse({"scores": [0.1, 0.8, 0.3]})

    monkeypatch.setattr("app.llm.rerank.bge_reranker.httpx.AsyncClient", _FakeClient)
    out = await reranker.rerank("q", ["a", "b", "c"], top_n=3)
    assert out[0].text == "b"  # score 0.8 最高
    assert out[1].text == "c"  # 0.3


@pytest.mark.asyncio
async def test_bge_reranker_dashscope_format(monkeypatch):
    """DashScope 后端：URL 走原生路径，请求体嵌套 input/parameters，响应用 relevance_score。"""
    reranker = BGEReranker(
        api_key="k",
        base_url="https://llm-xxx.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        model="qwen3-rerank",
    )
    assert reranker._is_dashscope()

    captured = {}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeRerankResponse(
                {"output": {"results": [
                    {"index": 0, "relevance_score": 0.9},
                    {"index": 2, "relevance_score": 0.4},
                    {"index": 1, "relevance_score": 0.1},
                ]}}
            )

    monkeypatch.setattr("app.llm.rerank.bge_reranker.httpx.AsyncClient", _FakeClient)
    out = await reranker.rerank("违约", ["d0", "d1", "d2"], top_n=3)
    # URL 走原生 rerank 路径，不是 /rerank
    assert captured["url"].endswith("/api/v1/services/rerank/text-rerank/text-rerank")
    # 请求体嵌套 input/parameters
    assert captured["json"]["input"]["query"] == "违约"
    assert captured["json"]["input"]["documents"] == ["d0", "d1", "d2"]
    assert captured["json"]["parameters"]["top_n"] == 3
    # 响应按 relevance_score 排序
    assert out[0].text == "d0" and out[0].score == 0.9
    assert out[1].text == "d2" and out[1].score == 0.4
    assert out[2].text == "d1" and out[2].score == 0.1
    assert all(c.index is not None for c in out)


@pytest.mark.asyncio
async def test_rerank_service_uses_real_when_available(monkeypatch):
    reranker = BGEReranker(api_key="k", base_url="http://rerank")
    svc = RerankService(reranker=reranker)

    called = {"real": False}

    async def _fake_rerank(query, docs, top_n=5):
        called["real"] = True
        return [RerankCandidate(text=d, score=0.99) for d in docs]

    monkeypatch.setattr(reranker, "rerank", _fake_rerank)
    out = await svc.rerank("q", ["d1", "d2"], top_n=2)
    assert called["real"]
    assert all(c.score == 0.99 for c in out)


@pytest.mark.asyncio
async def test_rerank_service_fallback_on_api_error(monkeypatch):
    reranker = BGEReranker(api_key="k", base_url="http://rerank")
    svc = RerankService(reranker=reranker)

    async def _raise(query, docs, top_n=5):
        raise RuntimeError("api down")

    monkeypatch.setattr(reranker, "rerank", _raise)
    out = await svc.rerank("合同 法律", ["合同法律文本", "无关"], top_n=2)
    # 退到 rerank_simple
    assert len(out) == 2
    assert out[0].score >= out[1].score


@pytest.mark.asyncio
async def test_rerank_service_simple_when_unavailable(monkeypatch):
    from app.configs import settings as settings_mod
    from app.llm.rerank import bge_reranker

    # BGEReranker 从 settings 读 env；想测"不可用"分支必须把 settings 也清空
    monkeypatch.setattr(bge_reranker.settings, "RERANK_API_KEY", "")
    monkeypatch.setattr(bge_reranker.settings, "RERANK_BASE_URL", "")
    reranker = BGEReranker(api_key="", base_url="")
    svc = RerankService(reranker=reranker)
    assert not reranker.available()
    out = await svc.rerank("合同", ["合同文本", "无关"], top_n=2)
    assert out[0].text == "合同文本"


# ---------- 3.2 jieba ----------

def test_tokenize_fallback_no_jieba(monkeypatch):
    import app.rag.retrieval.bm25 as bm25_mod

    monkeypatch.setattr(bm25_mod, "_JIEBA_AVAILABLE", False)
    tokens = bm25_mod.tokenize("合同法 第三条")
    assert "合" in tokens and "条" in tokens


def test_tokenize_with_jieba(monkeypatch):
    import app.rag.retrieval.bm25 as bm25_mod

    class _FakeJieba:
        @staticmethod
        def cut_for_search(text):
            return ["合同", "法", " ", "第三条"]

    monkeypatch.setattr(bm25_mod, "_JIEBA_AVAILABLE", True)
    monkeypatch.setattr(bm25_mod, "jieba", _FakeJieba, raising=False)
    tokens = bm25_mod.tokenize("合同法 第三条")
    assert "合同" in tokens
    assert "第三条" in tokens


# ---------- 3.3 Query 改写 ----------

class _StubLLM(LLMProvider):
    def __init__(self, response: str):
        self._response = response

    async def generate(self, messages, **kwargs):
        return self._response

    async def stream(self, messages, **kwargs):
        yield self._response

    async def embed(self, texts, **kwargs):
        return [[0.0] for _ in texts]


def test_should_rewrite_skips_short():
    assert not _should_rewrite("你好")


def test_should_rewrite_skips_simple_long():
    assert not _should_rewrite("什么是民法典里的民事法律行为有效条件")


def test_should_rewrite_triggers_on_reference():
    assert _should_rewrite("它的适用范围是什么，和上一个问题对比")


def test_should_rewrite_triggers_on_multi_question():
    assert _should_rewrite("合同效力与违约责任及损失赔偿")


@pytest.mark.asyncio
async def test_query_rewriter_returns_original_for_simple():
    rw = QueryRewriter(_StubLLM('["不该被调用"]'))
    out = await rw.rewrite("你好")
    assert out == ["你好"]


@pytest.mark.asyncio
async def test_query_rewriter_decomposes_complex():
    raw = json.dumps(["原查询", "合同效力", "违约责任"], ensure_ascii=False)
    rw = QueryRewriter(_StubLLM(raw))
    out = await rw.rewrite("合同效力与违约责任及损失赔偿")
    assert len(out) >= 2
    assert out[0] == "合同效力与违约责任及损失赔偿"  # 原 query 在首位


@pytest.mark.asyncio
async def test_query_rewriter_fallback_on_parse_failure():
    rw = QueryRewriter(_StubLLM("not json at all"))
    out = await rw.rewrite("合同效力与违约责任及损失赔偿")
    assert out == ["合同效力与违约责任及损失赔偿"]


# ---------- 3.5 domain 过滤 ----------

@pytest.mark.asyncio
async def test_vector_search_domain_filter_sql_shape():
    """vector_search 在 sqlite 上因 pgvector <=> 算子不可执行，仅校验 SQL 构造含 domain join。"""
    import inspect
    from app.database.repositories import document_repo as repo_mod

    src = inspect.getsource(repo_mod.DocumentRepo.vector_search)
    assert "join(Document" in src
    assert "Document.domain == domain" in src


@pytest.mark.asyncio
async def test_list_chunks_by_domain(db):
    from app.database.repositories.document_repo import DocumentRepo

    repo = DocumentRepo(db)
    legal_doc = await repo.create_document(domain="legal", title="l", source="s")
    finance_doc = await repo.create_document(domain="finance", title="f", source="s")
    await repo.create_chunk(document_id=legal_doc.id, content="legal1", metadata={})
    await repo.create_chunk(document_id=legal_doc.id, content="legal2", metadata={})
    await repo.create_chunk(document_id=finance_doc.id, content="fin1", metadata={})
    await db.flush()

    chunks = await repo.list_chunks_by_domain("legal", limit=100)
    assert len(chunks) == 2
    assert all(c.document_id == legal_doc.id for c in chunks)


@pytest.mark.asyncio
async def test_bm25_search_with_domain_filter(db):
    from app.rag.retrieval.bm25 import BM25Retriever
    from app.database.repositories.document_repo import DocumentRepo

    repo = DocumentRepo(db)
    legal_doc = await repo.create_document(domain="legal", title="l", source="s")
    finance_doc = await repo.create_document(domain="finance", title="f", source="s")
    await repo.create_chunk(document_id=legal_doc.id, content="民法典 合同编", metadata={})
    await repo.create_chunk(document_id=finance_doc.id, content="基金 收益率", metadata={})
    await db.flush()

    retriever = BM25Retriever(db=db, repo=repo)
    results = await retriever.search("合同", top_k=5, domain="legal")
    assert all(c.document_id == legal_doc.id for c in results)
    assert len(results) == 1
    assert "合同" in results[0].content


@pytest.mark.asyncio
async def test_rag_service_search_with_domain(db):
    from app.rag.service import RAGService
    from app.database.repositories.document_repo import DocumentRepo

    repo = DocumentRepo(db)
    legal_doc = await repo.create_document(domain="legal", title="l", source="s")
    finance_doc = await repo.create_document(domain="finance", title="f", source="s")
    await repo.create_chunk(document_id=legal_doc.id, content="民法典 合同编", metadata={})
    await repo.create_chunk(document_id=finance_doc.id, content="基金 收益率", metadata={})
    await db.flush()

    svc = RAGService(db=db, mode="bm25")
    results = await svc.search("合同", top_k=5, domain="legal")
    assert all(c.document_id == legal_doc.id for c in results)


@pytest.mark.asyncio
async def test_rag_cache_hit(db, monkeypatch):
    """检索缓存命中：同 query 第二次走缓存（依赖模块 04 Redis，用 FakeRedis mock）。"""
    from app.services import redis as redis_mod
    from app.rag.service import RAGService
    from app.database.repositories.document_repo import DocumentRepo

    # 注入 FakeRedis
    fake = _FakeRedisForRag()
    monkeypatch.setattr(redis_mod, "_client", fake)
    monkeypatch.setattr(redis_mod, "_initialized", True)

    repo = DocumentRepo(db)
    doc = await repo.create_document(domain="legal", title="t", source="s")
    await repo.create_chunk(document_id=doc.id, content="民法典 合同编", metadata={})
    await db.flush()

    svc = RAGService(db=db, mode="bm25")
    r1 = await svc.search("合同", top_k=2)
    assert len(r1) >= 1
    # 第二次应命中缓存
    r2 = await svc.search("合同", top_k=2)
    assert len(r2) == len(r1)
    assert r2[0].content == r1[0].content


class _FakeRedisForRag:
    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, k):
        return self._store.get(k)

    async def set(self, k, v, ex=None):
        self._store[k] = v

    async def delete(self, k):
        return self._store.pop(k, None) and 1 or 0

    async def scan_iter(self, match=None, count=100):
        import fnmatch

        for k in list(self._store.keys()):
            if match is None or fnmatch.fnmatch(k, match):
                yield k
