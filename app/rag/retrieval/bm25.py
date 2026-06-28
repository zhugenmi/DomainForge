from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chunk import DocumentChunk
from app.database.repositories.document_repo import DocumentRepo
from app.observability.logging.logger import get_logger

logger = get_logger("rag.bm25")

_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)

# jieba 为可选依赖：可用则中文按词切，提升短语级召回；不可用退化为字切。
try:
    import jieba  # type: ignore

    _JIEBA_AVAILABLE = True
except ImportError:
    _JIEBA_AVAILABLE = False


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def tokenize(text: str) -> list[str]:
    """分词：jieba 可用时中文按词切，否则 CJK 按字 + 其他按词。"""
    if not text:
        return []
    if _JIEBA_AVAILABLE:
        return [t for t in jieba.cut_for_search(text.lower()) if t.strip()]
    # 退路：CJK 按字，其他按词
    tokens: list[str] = []
    for w in _TOKEN_RE.findall(text.lower()):
        if any(_is_cjk(c) for c in w):
            tokens.extend(list(w))
        else:
            tokens.append(w)
    return tokens


@dataclass
class BM25Doc:
    id: object
    tokens: list[str]


class BM25Index:
    """进程内 BM25，用于无 PG 全文索引环境的退路。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[BM25Doc] = []
        self.df: Counter[str] = Counter()
        self.avg_len: float = 0.0

    def add(self, doc_id: object, text_content: str) -> None:
        toks = tokenize(text_content)
        self.docs.append(BM25Doc(id=doc_id, tokens=toks))
        for t in set(toks):
            self.df[t] += 1
        self.avg_len = sum(len(d.tokens) for d in self.docs) / max(1, len(self.docs))

    def search(self, query: str, top_k: int = 10) -> list[tuple[object, float]]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        n = len(self.docs)
        scores: list[tuple[object, float]] = []
        for d in self.docs:
            tf = Counter(d.tokens)
            score = 0.0
            for t in q_tokens:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                denom = tf[t] + self.k1 * (1 - self.b + self.b * len(d.tokens) / max(1, self.avg_len))
                score += idf * (tf[t] * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((d.id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def _is_postgres(db: AsyncSession) -> bool:
    return db.bind and db.bind.dialect.name == "postgresql"


class BM25Retriever:
    """PG 全文检索（生产）+ 进程内 BM25（测试/无 PG 时退路）。"""

    def __init__(self, db: AsyncSession, repo: DocumentRepo | None = None):
        self.db = db
        self.repo = repo or DocumentRepo(db)

    async def search(self, query: str, top_k: int = 10, domain: str | None = None) -> list[DocumentChunk]:
        if _is_postgres(self.db):
            try:
                return await self._search_pg(query, top_k, domain)
            except Exception:
                pass
        return await self._search_fallback(query, top_k, domain)

    async def _search_pg(self, query: str, top_k: int, domain: str | None) -> list[DocumentChunk]:
        escaped = query.replace("'", "''")
        if domain is not None:
            sql = text(
                "SELECT dc.* FROM document_chunks dc "
                "JOIN documents d ON dc.document_id = d.id "
                "WHERE dc.tsv @@ plainto_tsquery('simple', :q) AND d.domain = :domain "
                "ORDER BY ts_rank(dc.tsv, plainto_tsquery('simple', :q)) DESC "
                "LIMIT :k"
            )
            result = await self.db.execute(sql, {"q": escaped, "domain": domain, "k": top_k})
        else:
            sql = text(
                "SELECT * FROM document_chunks "
                "WHERE tsv @@ plainto_tsquery('simple', :q) "
                "ORDER BY ts_rank(tsv, plainto_tsquery('simple', :q)) DESC "
                "LIMIT :k"
            )
            result = await self.db.execute(sql, {"q": escaped, "k": top_k})
        rows = result.mappings().all()
        chunks: list[DocumentChunk] = []
        for row in rows:
            c = DocumentChunk(
                id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                metadata_=row.get("metadata") or {},
            )
            chunks.append(c)
        return chunks

    async def _search_fallback(self, query: str, top_k: int, domain: str | None) -> list[DocumentChunk]:
        if domain is not None:
            all_chunks = await self.repo.list_chunks_by_domain(domain, limit=1000)
        else:
            result = await self.db.execute(select(DocumentChunk).limit(1000))
            all_chunks = list(result.scalars().all())
        # 检索结果只读快照，从 session 分离，避免写检索分数时被 dirty tracking 持久化进 DB
        for c in all_chunks:
            self.db.expunge(c)
        idx = BM25Index()
        for c in all_chunks:
            idx.add(c.id, c.content)
        ranked = idx.search(query, top_k=top_k)
        id_to_chunk = {c.id: c for c in all_chunks}
        out: list[DocumentChunk] = []
        for cid, score in ranked:
            c = id_to_chunk.get(cid)
            if c:
                c.score = float(score)
                out.append(c)
        return out


__all__ = ["BM25Retriever", "BM25Index", "tokenize"]
