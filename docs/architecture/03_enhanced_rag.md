# 03 增强检索：BM25 + 向量 + RRF + Rerank 领域问答

> 版本：0.1.0 | 日期：2026-06-17 | 对应代码：`app/rag/`、`app/llm/rerank/`、`app/llm/embedding/`

---

## 1. 设计目标

在 PostgreSQL + pgvector 上构建一套**召回率高、可解释、可降级**的混合检索管线，支撑法律、金融等垂直领域的精准问答。

核心指标：

- **召回率**：单路检索覆盖不全时，双路并行 + RRF 融合补齐。
- **精度**：召回后用 CrossEncoder-style rerank 重排，取真正相关的 top_k。
- **可降级**：pgvector / PG 全文索引不可用时（如测试用 SQLite），自动退化为进程内算法，不阻塞链路。

---

## 2. 数据底座

### 2.1 表结构

| 表 | 关键字段 | 说明 |
|----|---------|------|
| `documents` | id, domain, title, source, file_type | 文档元信息 |
| `document_chunks` | id, document_id, content, **embedding (vector(1024))**, **metadata_ (JSON)**, **tsv (tsvector)**, score | 分块 + 向量 + 全文索引 + 元数据 |
| `categories` | domain, name, description | 领域分类，预置 legal / finance |

### 2.2 索引

- **向量索引**：pgvector 的 `ivfflat` 或 `hnsw`（按 `EMBEDDING_DIMENSION=1024` 建）。
- **全文索引**：`tsv` 列上建 GIN 索引，供 BM25Retriever 的 PG 路径使用 `plainto_tsquery('simple', :q)` + `ts_rank` 排序。
- **JSON 兼容**：`metadata_` 用 `JSON`（SQLAlchemy 通用类型），PG 上自动映射为 JSONB，SQLite 上映射为 TEXT——保证测试可跑。

### 2.3 向量类型容错

`app/database/models/chunk.py::_vector_type()` 延迟导入 pgvector：导入成功用 `Vector(1024)`，失败 fallback 为 `Text`。这让无 pgvector 的环境（CI、本地 SQLite）仍能建表。

---

## 3. 文档解析与分块

### 3.1 解析器矩阵

`app/rag/parser/`

| 格式 | 解析器 | 依赖 |
|------|--------|------|
| md / markdown | `parse_markdown` | markdown-it-py |
| html / htm | `parse_html` | beautifulsoup4 |
| pdf | `parse_pdf` | pypdf |
| docx | `parse_docx` | python-docx |
| xlsx / xls | `parse_xlsx` | openpyxl |
| txt / other | 直接 `read_text` | — |

`parse(path)` 与 `parse_bytes(filename, data)` 双入口：前者服务本地索引脚本，后者服务 HTTP 上传。`detect_file_type(filename)` 返回标准化类型标签写入 `documents.file_type`。

> **本次清理**：删除了 `parse_text`（无操作的 `return text`），它从未被引用。

### 3.2 领域分块策略

`app/rag/chunk/`

| 分块器 | 策略 | 元数据键 |
|--------|------|---------|
| `chunk_semantic` | 段落 + 句子边界，`chunk_size=500`、`overlap=50`，超长句硬切 | `chunk_index` |
| `chunk_legal` | 按"第X条"正则切分 | `chunk_index` + `article` |
| `chunk_finance` | 按标题层级正则切分（`# 标题` / `第X章` / `1.1 标题`） | `chunk_index` + `heading` |

**复用机制**（本次优化）：`legal_chunker` 与 `finance_chunker` 原本是近乎复制的"正则找边界 → 切片 → 退化段落"流程。已抽取公共函数 `semantic_chunker.split_by_pattern(text, pattern, meta_key, metadata)`，两个领域分块器各只保留 3 行（编译正则 + 调 `split_by_pattern`）。新增领域分块器（如医疗按"主诉/现病史"切）只需定义正则 + meta_key。

### 3.3 索引管线

`app/rag/indexing/pipeline.py::IndexingPipeline`

```python
async def index_text(domain, title, content, source, chunk_strategy, chunk_size, chunk_overlap):
    doc = await repo.create_document(domain, title, source)
    chunks = self._chunk(content, chunk_strategy, ...)   # semantic / legal / finance
    embeddings = await self.embedder.embed([c.text for c in chunks])  # 分批
    for c, emb in zip(chunks, embeddings):
        await repo.create_chunk(document_id=doc.id, content=c.text, embedding=emb, metadata=c.metadata)
    metrics.inc("indexing.chunks", len(chunks))
```

`_chunk` 按 `chunk_strategy` 字符串分发：`"legal"` → `chunk_legal`，`"finance"` → `chunk_finance`，其他 → `chunk_semantic`。`chunk_strategy` 由 API 层根据 `domain` 推断（legal 域默认 legal 策略）。

`embedder.embed` 内部按 `EMBEDDING_BATCH_SIZE` 切片，避免 DashScope 单批 ≤10 的限制。

---

## 4. 三路检索器

### 4.1 VectorRetriever

`app/rag/retrieval/vector.py`

1. `embedder.embed([query])` 得到查询向量。
2. `DocumentRepo.vector_search` 执行 pgvector 余弦距离 `<=>` 检索。
3. SQLite 退路：全表扫描 + Python 余弦相似度（仅测试用）。

### 4.2 BM25Retriever

`app/rag/retrieval/bm25.py`

**双路径设计**：

- **PG 路径**（生产）：`SELECT * FROM document_chunks WHERE tsv @@ plainto_tsquery('simple', :q) ORDER BY ts_rank(tsv, ...) DESC LIMIT :k`。
- **退路**（测试/无 PG）：加载全表（≤1000 行），用进程内 `BM25Index`（k1=1.5, b=0.75）计算分数。

`_is_postgres(db)` 判断方言；PG 路径异常时 `try/except` 静默退化到进程内，保证可用性。

**分词**：`tokenize` 对 CJK 按字切、其他按词切（`re.findall(r"[\w]+")` + CJK 范围检测）。无 jieba 依赖，避免部署复杂度；代价是中文短语级召回略弱，靠 rerank 补救。

### 4.3 HybridRetriever（核心）

`app/rag/retrieval/hybrid.py`

```python
async def search(query, top_k=5, rerank_top_n=5):
    vec = await vector.search(query, top_k=max(top_k*3, 10))    # 召回放宽
    bm  = await bm25.search(query, top_k=max(top_k*3, 10))
    fused = rrf_fuse({"vector": [c.id for c in vec],
                      "bm25":   [c.id for c in bm]},
                     top_n=max(rerank_top_n*2, 10))             # RRF 融合
    candidates = [id_to_chunk[r.doc_id] for r in fused]
    reranked = await rerank.rerank(query, [c.content for c in candidates], top_n=rerank_top_n)
    # 用文本回溯 chunk，写回 score
    return out[:top_k]
```

**召回放宽**：双路各取 `top_k*3`（至少 10），给 RRF 与 rerank 足够候选池。最终只返回 `top_k`。

### 4.4 RRF 融合

`app/rag/retrieval/rrf.py`

```python
def rrf_fuse(ranked_lists: dict[str, list[Any]], k=60, top_n=None) -> list[RRFResult]:
    for source, lst in ranked_lists.items():
        for rank, doc_id in enumerate(lst):
            scores[doc_id] += 1.0 / (k + rank + 1)
    ...
```

`k=60` 是 RRF 论文默认值，平衡头部与尾部权重。返回 `RRFResult(doc_id, score, source_ranks)`，`source_ranks` 记录每路中的名次，便于调试"这个文档为什么排上来"。

### 4.5 Rerank

`app/llm/rerank/`

- `BGEReranker`：封装 BGE reranker API（HTTP），`available()` 检查 endpoint 是否配置。
- `RerankService.rerank`：reranker 不可用时走 `rerank_simple`（基于关键词重叠的轻量打分），保证链路不阻塞。

> **演进状态**(Phase 5/12 后):`RerankService.rerank` 已放开真实 API 调用,三段式 `available -> try real -> except fallback to simple`。`RerankService()` 无参构造按 `settings.RERANK_MODEL` 名字自动选 `QwenReranker`(DashScope 扁平体,含 `qwen`)或 `BGEReranker`(BGE 兼容)。真实 rerank 失败兜底 `rerank_simple` 关键词重叠。详见 [fix/2026-06-27-rerank-not-effective.md](../fix/2026-06-27-rerank-not-effective.md)(三个叠加 bug 的修复全过程)。

---

## 5. 统一入口：RAGService

`app/rag/service.py`

```python
class RAGService:
    def __init__(self, db, retriever=None, llm=None, mode: RetrievalMode = "hybrid")
    async def search(query, top_k=5, mode=None) -> list[DocumentChunk]
```

`RetrievalMode = Literal["vector", "bm25", "hybrid"]`。`mode` 可构造时定死，也可每次调用时覆盖。

- `vector` → `VectorRetriever`
- `bm25` → `BM25Retriever`
- `hybrid` → `HybridRetriever`（需 llm 用于 query embedding）

`hybrid` 模式下若 `llm is None`（无法 embed query），自动退化到 `bm25`，避免硬错。

API 层 `/knowledge/search?mode=hybrid|vector|bm25` 透传到 `RAGService.search(mode=...)`。

---

## 6. 上下文组装与引用

`app/rag/context/`

- `builder.ContextBuilder`：把检索到的 chunks 拼成 LLM 可用的 system prompt，控制总长度（避免超 context window）。
- `citation.Citation`：为答案生成 `[1] [2]` 风格的引用标记，回指 `document_id` + `chunk_index`，支撑"答案可溯源"。

AnswerNode 消费 ContextBuilder 的输出，最终答案带引用编号，前端可渲染为可点击的来源链接。

---

## 7. 检索链路全景

```
query
  │
  ├──→ VectorRetriever ──→ pgvector cosine ──→ top 30
  │                                            │
  ├──→ BM25Retriever ────→ PG tsv / 进程内 ──→ top 30
  │                                            │
  └────────────── RRF fuse (k=60) ─────────────┴──→ top 20 候选
                                                     │
                                              RerankService
                                              (BGE / simple)
                                                     │
                                                     ▼
                                              top_k=5 带分数
                                                     │
                                              ContextBuilder
                                                     │
                                              AnswerNode 生成答案 + 引用
```

---

## 8. 当前限制

1. **Rerank 未启用真实模型**:**已解除**(Phase 5/12)。见 §4.5,真实 BGE/Qwen rerank 已启用,失败兜底 `rerank_simple`。
2. **BM25 中文分词粗糙**:**部分解除**(Phase 5)。`tokenize` jieba 可选(`[cn]` extra),`cut_for_search` 模式;无 jieba 退字切。PG 路径仍用 `plainto_tsquery('simple', :q)`,生产可装 `zhparser` 扩展。
3. **无 query 改写**:**已解除**(Phase 5)。`QueryRewriter.rewrite(query, history)` 做指代消解 + 子查询分解,跳过门控短查询/无指代词直接返回 `[query]`,每个子查询各跑双路召回合并。
4. **无检索结果缓存**:**已解除**(Phase 6)。`RAGService.search` 入口缓存 `(mode, top_k, domain, query)` hash,TTL 15min;知识库 confirm/delete 时 `cache_clear_prefix("rag:")`。
5. **Chunk 元数据未用于过滤**:**已解除**(Phase 5)。`DocumentRepo.vector_search` / `BM25Retriever` 加 `domain` 参数,JOIN documents + WHERE domain 下推。

> **引用增强**(Phase 11/12):`RetrievalNode` 保留 chunk id/score/metadata,`AnswerNode` 用 `build_context` 生成 `[N]` 编号上下文,`reorder_citations` 按出现顺序重编号,`Citation` 含 title/chapter/locator/snippet 定位。LLM 只标正文 `[N]`,参考列表后端结构化下发。详见 [fix/2026-06-28-citation-reorder-locator.md](../fix/2026-06-28-citation-reorder-locator.md) 与 [fix/2026-06-27-citation-chapter-missing.md](../fix/2026-06-27-citation-chapter-missing.md)。

> **异步导入**(Phase 11):`POST /knowledge/confirm` 改 `202 + job_id`,后台 `_run_import` 跑 embed+persist,前端轮询 `GET /knowledge/import/{job_id}/status` 获取 chunk 级进度。详见 [adr/0004-async-import-over-sync.md](../adr/0004-async-import-over-sync.md)。