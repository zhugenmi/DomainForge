# ADR 0001:向量检索用 pgvector 而非独立向量库

> 状态:已采纳 | 日期:2026-06-17

## 背景

领域问答需要向量检索能力。生态中有两类选择:
- **独立向量库**:Chroma、Qdrant、Milvus、Weaviate
- **PostgreSQL 扩展**:pgvector

项目已用 PostgreSQL 作主库存 users/sessions/messages/documents/audit_logs,需另选向量存储。

## 决策

采用 **pgvector**(PostgreSQL 扩展),不引入独立向量库。

## 理由

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| Chroma | 单独进程,运维多一套;事务与 PG 不一致,知识库删除时需双写清理 |
| Qdrant / Milvus | 高性能但重,本项目语料规模(万级 chunk)用不上分布式向量库能力 |
| Weaviate | 自带 schema 与 GraphQL,与现有 SQLAlchemy 栈重复 |

### 选 pgvector 的理由

1. **单数据库统一**:向量与关系数据在同一 PG 实例,`document_chunks` 与 `documents` 同库 JOIN。domain 过滤(向量召回 + `WHERE documents.domain = 'legal'`)是单 SQL,无需跨库协调。
2. **事务一致**:文档删除(`DELETE FROM documents`)级联清 chunks + embedding,同一事务内完成,无残影。
3. **运维零增量**:PG 已在栈内,`CREATE EXTENSION vector` 即可,无新进程、无新端口、无新备份策略。
4. **性能足够**:pgvector 的 ivfflat/hnsw 索引在万级 chunk 下毫秒级返回(实测 p50 592ms 含 rerank 网络往返,见 [eval/2026-07-01-runtime-performance.md](../eval/2026-07-01-runtime-performance.md))。百万级以上才需考虑独立向量库。
5. **SQLite 测试可跑**:`_vector_type()` 延迟导入 + Text fallback,让测试用 SQLite 也能建表(见 [fix/2026-06-17-sqlite-jsonb-pgvector-compat.md](../fix/2026-06-17-sqlite-jsonb-pgvector-compat.md))。

## 后果

- **正面**:栈简化,事务一致,domain 过滤下推到 SQL,运维零增量。
- **负面**:pgvector 的 HNSW 索引构建慢于专用向量库;百万级 chunk 后需重建索引或分表。
- **迁移成本**:若未来切独立向量库,需改 `DocumentRepo.vector_search` + 引入双写,但 `RAGService` 接口不变,Runtime 零感知。
