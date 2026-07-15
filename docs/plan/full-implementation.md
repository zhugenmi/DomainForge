# DomainForge 完整实现计划

> 状态：**主体完成，剩余加固项另立模块计划** | 范围：`app/` + `frontend/` + `scripts/` + `tests/` | 基线：`design.md`
> 最近修订：2026-07-09（文档结构调整）

## 0. 现状基线

### 已实现（对照 `design.md` 第 22 节优先级）

| 模块 | 状态 | 关键文件 |
|------|------|---------|
| API 与会话骨架 | ✅ | `app/api/` 8 个 router，18+ 端点 |
| 单模型问答 | ✅ | `app/llm/providers/openai.py` |
| 流式输出 (SSE) | ✅ | `app/runtime/events/event_bus.py`、`app/api/chat.py` |
| 工具注册与调用 | ✅ | `app/tools/registry/`、`app/tools/builtin/`（calculator/knowledge/sql/file/search）、`app/runtime/nodes/tool_node.py` |
| Agent Runtime 状态机 | ✅ | `app/runtime/`（State + Node + Router，含 `ConditionalStrategy` + Reflection 闭环） |
| 记忆模块 | ✅ | `app/memory/`（short_term/summary/long_term + `MemoryService`） |
| 知识库解析与检索 | ✅ | `app/rag/`（parser 6 格式、chunk 3 策略、retrieval vector/bm25/hybrid/rrf、indexing、context、`RAGService`） |
| RRF + Rerank | ✅ (Rerank 退化为关键词重叠，见下) | `app/rag/retrieval/rrf.py`、`app/llm/rerank/` |
| 安全与权限 | ✅ | `app/security/`（jwt/auth/permission/prompt_guard/content_filter） |
| Tracing 与 Evals | ✅ (自研 Tracing，未接 OTel SDK) | `app/observability/`、`app/evals/` |
| 模型路由 + 降级 | ✅ (Fallback 已实现但未接入主链路) | `app/llm/router/` |
| 前端 | ✅ 浅色专业风，5 路由（对话/知识/技能/审计/评测） | `frontend/src/app/(app)/` |
| 脚本 | ✅ | `scripts/`（build_index/import_documents/run_evals/benchmark） |

### 原 gap 全部解除(2026-06-27 六模块加固完成)

以下原 gap 已全部解决,详见对应架构文档与 fix/adr 记录:

| 原 gap | 解决方案 | 详见 |
|---|---|---|
| Rerank 真实模型未启用 | Phase 5/12 启用真实 BGE/Qwen rerank,失败兜底 `rerank_simple` | [architecture/03](../architecture/03_enhanced_rag.md) §4.5 + [fix/2026-06-27-rerank-not-effective.md](../fix/2026-06-27-rerank-not-effective.md) |
| Fallback 未接入主链路 | Phase 4 改用 `get_fallback()` 返回 `FallbackPolicy` | [architecture/02](../architecture/02_model_capability.md) §2.5 |
| MCP 适配器未注册 | Phase 8 `MCPToolAdapter` 适配进 registry + 敏感工具二次确认 | [architecture/02](../architecture/02_model_capability.md) §4 |
| ToolNode 绕过 LLMProvider | Phase 4 `chat_with_tools` 抽象 + 默认抛 NotImplementedError | [adr/0006](../adr/0006-llmprovider-default-not-implemented.md) |
| Redis 未接入 | Phase 6 缓存/限流/共享 session/检索缓存 + 优雅降级 | [architecture/04](../architecture/04_backend_service.md) §5 |
| 未接 OTel SDK | Phase 7 迁移到 OTel SDK + LLM-as-judge | [architecture/05](../architecture/05_observability_evals.md) §5 |
| JWT_SECRET 弱 / CORS 宽 / PreviewStore 单实例 | Phase 3 强密钥校验 + PBKDF2 + CORS 收紧;Phase 6 PreviewStore Redis 后端 | [architecture/04](../architecture/04_backend_service.md) §6/§8 + [adr/0003](../adr/0003-pbkdf2-over-bcrypt.md) |

### 后续工作

原 01-06 模块计划文件已删除(内容沉淀到 architecture/ + fix/ + adr/)。后续新需求直接在对应 `architecture/0X_*.md` 的"当前限制与后续"章节记录,bug 修复在 `fix/` 新建 `YYYY-MM-DD-slug.md`,技术选型在 `adr/` 新建 `00XX-slug.md`。

## 1. 实施原则

遵循 `CLAUDE.md`：
1. **最小可用**：每个模块实现到"可调用 + 可测试"为止，不引入未被 design.md 列出的能力。
2. **外科式改动**：已工作代码保持向后兼容，新增以扩展点接入。
3. **可验证**：每个模块至少 1 个单测或集成测试；`pytest -q` 必须全绿。

## 2. 后端模块实施清单（已落地回顾）

### 2.1 LLM 层（`app/llm/`）— ✅ 完成
- `providers/deepseek.py`、`glm.py`、`qwen.py`、`gemini.py`：均继承 `OpenAIProvider`，仅 override `base_url`/`model` 默认值（国内主流厂商均 OpenAI 兼容）。
- `router/model_router.py`：`ModelRouter`，根据 provider 偏好返回 provider；`get_chat_llm()` / `get_fallback()`。
- `router/fallback.py`：`FallbackPolicy`，捕获异常后切备用 provider，记录 `failures` 列表。
- `embedding/embedding_service.py`：统一 `embed(texts)->list[list[float]]`，底层复用 `OpenAIProvider.embed`，分批避免超限。
- `rerank/rerank_service.py`、`bge_reranker.py`、`qwen_reranker.py`：`RerankService.rerank(query, docs, top_n)` 三段式(真实 API -> 失败兜底 `rerank_simple` -> 未配置走 simple)。Phase 5/12 已启用真实 BGE/Qwen rerank,详见 [architecture/03](../architecture/03_enhanced_rag.md) §4.5。

**验证**：`test_model_router`、`test_fallback`、rerank 真实/降级路径测试已通过。

### 2.2 Runtime 编排（`app/runtime/`）
- `planner/planner.py` + `task_decomposer.py` + `prompt.py`：`PlannerNode`，对复杂 query 用 LLM 输出 JSON 计划 `[{step, action}]`，写入 `state.plan`，并发布 `PLAN_GENERATED` 事件；简单意图跳过规划。
- `reflection/evaluator.py` + `critic.py` + `retry_policy.py`：`ReflectionNode`，调用 LLM 评估"答案是否充分/是否需要重检"；不充分且 `retries < max_retries` 时增加 `retries` 并触发 `retrieval`/`tool` 重跑（受 `max_iterations` 上限保护）。
- `router/condition.py` + `strategy.py`：`Router` 升级为**条件路由**——根据 `state.intent` 与 `state.plan` 决定下一步节点；保留线性 fallback。
- `events/publisher.py`：封装 `EventPublisher`，给 audit 与 tracing 复用。
- `runtime.py`：装配条件路由 + 反思闭环；`max_iterations` 默认 6。

**验证**：扩展 `test_router` 覆盖条件分支；新增 `test_reflection_retry`。

### 2.3 Tools（`app/tools/`）
- `builtin/search_tool.py`：基于 DuckDuckGo HTML（httpx，无 key）；返回 top N 摘要。
- `builtin/sql_tool.py`：只读 SQL 执行器（白名单 SELECT，连接独立只读 DSN，受 `permission_scope="sensitive"` 限制）。
- `builtin/file_tool.py`：读/写本地 `data/uploads/`（沙箱化，禁绝对路径越界）。
- `mcp/client.py`：`MCPClient` 抽象（list_tools / call_tool），暂以 stub 实现 + 文档说明，符合 design 第 7 节"统一接口"要求。

**验证**：`test_search_tool_offline`（mock httpx）、`test_sql_tool_rejects_write`、`test_file_tool_sandbox`。

### 2.4 RAG（`app/rag/`）
- `parser/markdown_parser.py`、`html_parser.py`、`pdf_parser.py`、`docx_parser.py`：纯 Python 解析；PDF/DOCX 用 `pypdf`/`python-docx`（加入可选依赖）。
- `chunk/semantic_chunker.py`（按段落 + 句子重叠）、`legal_chunker.py`（按"第X条"切分）、`finance_chunker.py`（按标题层级切分）。
- `retrieval/bm25.py`：基于 PG `to_tsvector('chinese_zh', content)` + `ts_rank`；中文分词退化到字符级 tsvector（避免 jieba 依赖）。
- `retrieval/rrf.py`：两路 list 融合，`k=60`。
- `retrieval/hybrid.py`：组合 vector + bm25 → rrf → rerank。
- `indexing/pipeline.py`：`IndexingPipeline.run(document)` = parse → chunk → embed → persist。
- `context/builder.py` + `citation.py`：拼装上下文 + 生成 `[doc:chunk_id]` 引用。
- `service.py`：升级 `search` 支持 `mode="vector"|"bm25"|"hybrid"`；默认 hybrid。

**验证**：`test_rrf_fusion`、`test_legal_chunker`、`test_context_builder_citation`。

### 2.5 Memory（`app/memory/`）
- `summary/summary_memory.py`：超过阈值轮数时调 LLM 压缩成摘要存入 `memories` 表（`memory_type="summary"`）。
- `long_term/vector_memory.py`：用户偏好/事实型记忆，写入 `memories` 表 `type="long_term"` 并生成 embedding；查询时向量检索。
- `memory_service.py`：统一对外 `get_context(user_id, session_id)` = short_term + summary + long_term。

**验证**：`test_summary_memory_threshold`、`test_long_term_memory_recall`。

### 2.6 Security（`app/security/`）
- `jwt.py`：HS256 签发/校验；`auth.py`：FastAPI dependency `get_current_user`（从 `Authorization: Bearer`）；`permission.py`：RBAC `require_role("admin"|"operator"|"user")`。
- `prompt_guard.py`：检测 "ignore previous instructions" / "system prompt leak" / role override 模式。
- `content_filter.py`：基础关键词黑名单（可配置）。
- 默认 `dev` 模式下 `/chat` 放行匿名（保留现有默认用户），生产模式强制 JWT。

**验证**：`test_jwt_sign_verify`、`test_prompt_guard_detects_injection`、`test_require_role`。

### 2.7 Observability（`app/observability/`）
- `tracing/tracer.py`：`tracer.span(name)` contextmanager，生成 `trace_id` + `span_id`，记录到 `contextvars`；OTEL 端点配置时自动 export，否则仅日志。
- `tracing/decorators.py`：`@trace()` 装饰节点/工具/检索方法。
- `metrics/metrics.py`：计数器/计时器（进程内 dict + structlog 输出）。

**验证**：`test_tracer_span_nesting`、`test_metrics_counter`。

### 2.8 Evals（`app/evals/`）
- `datasets/legal/*.json`、`finance/*.json`：每领域 3-5 条样例。
- `metrics/correctness.py`、`groundedness.py`、`retrieval.py`：基于 LLM 评分 + 关键词命中。
- `runner.py`：`EvalRunner.run(dataset)` → 写入 `eval_results`（新增表，见 2.10）。
- `analyzer.py`：bad case 聚合。

**验证**：`test_eval_runner_with_mock_llm`。

### 2.9 API 新增（`app/api/`）
- `sessions.py`：`GET /sessions`、`GET /sessions/{id}`、`GET /sessions/{id}/messages`、`DELETE /sessions/{id}`。
- `audit.py`：`GET /audit/{trace_id}`。
- `evals.py`：`POST /evals/run`、`GET /evals/results`。
- `admin.py`：`GET /admin/tools`（列出注册工具）、`GET /admin/health/detail`。
- `main.py`：注册新 router；开启 CORS（允许前端 origin）。

**验证**：扩展 `test_chat` 覆盖 `/sessions`。

### 2.10 DB 补全
- 新增 model `EvalResult`（`eval_results` 表）；补 `UserRepo`、`MemoryRepo`。
- Alembic 新增 revision 包含 `eval_results` + `memories.embedding`（用于 long_term 向量召回，复用 pgvector）。
- 文档 chunks 增加 `tsv tsvector` 列 + GIN 索引（migration 中创建）。

## 3. 前端重设计（浅色风格）

**目标**：替换深空黑为浅色专业风，符合日常办公审美，保留现有信息架构并扩展新页面。

### 3.1 设计语言
| 维度 | 决定 |
|---|---|
| 调色 | 主背景 `#F7F8FA` / 卡片 `#FFFFFF` / 边线 `#E5E7EB` / 主文 `#1F2937` / 次文 `#6B7280` / 弱文 `#9CA3AF` / 强调蓝 `#2563EB` / 强调浅 `#EFF6FF` / 成功 `#10B981` / 危险 `#EF4444` |
| 字体 | 系统 sans（中文优先 PingFang/微软雅黑），代码用 ui-monospace |
| 圆角 | 卡片 12px / 按钮 8px / 输入 8px |
| 阴影 | 卡片 `0 1px 3px rgba(0,0,0,0.06)`；hover 加深 |
| 动效 | fade-up 200ms；hover 100ms；不滥用动效 |
| 强调 | 仅一个主蓝；状态色仅 success/danger |

### 3.2 信息架构扩展
- 侧栏：品牌 + 新会话 + **会话历史**（最近 N 条，可点击切换） + 知识库 + 技能 + 审计 + 评测 + 健康状态
- 顶部：面包屑 + 当前模块标题
- 页面：`/`（对话）、`/knowledge`、`/skills`、`/audit`、`/evals`

### 3.3 文件改动
- 替换 `globals.css`（浅色 token + 同套动画类名保留，便于组件无侵入迁移）
- 更新 `Sidebar.tsx`：浅色 + 会话历史区
- 重写 `ChatWorkspace.tsx`、`knowledge/*`、`skills/SkillsView.tsx` 为浅色
- 新增 `audit/AuditView.tsx`、`evals/EvalsView.tsx` + 对应 `app/audit/page.tsx`、`app/evals/page.tsx`
- 扩展 `lib/api.ts`：新增 `listSessions`、`getSessionMessages`、`deleteSession`、`getAudit`、`runEvals`、`listTools`

### 3.4 验证
- `npm run build` 0 错误
- 5 个路由可访问
- 对话 SSE 流式 + 历史切换可用

## 4. 脚本（`scripts/`）
- `build_index.py`：从 `data/raw_documents/` 批量建索引
- `import_documents.py`：CLI 导入单文件
- `run_evals.py`：跑指定数据集
- `benchmark.py`：测延迟/吞吐

## 5. 执行顺序

1. **后端基础设施**：security、observability、新 model/repo、alembic migration → `pytest` 绿
2. **LLM 扩展**：providers + router + embedding/rerank service → 测试绿
3. **Runtime 增强**：planner + reflection + 条件 router → 测试绿
4. **Tools**：search/sql/file/mcp → 测试绿
5. **RAG**：parser/chunk/bm25/rrf/hybrid/indexing/context → 测试绿
6. **Memory**：summary + long_term + service → 测试绿
7. **Evals**：datasets/metrics/runner/analyzer → 测试绿
8. **API**：sessions/audit/evals/admin → 测试绿
9. **前端**：globals.css + 各页面浅色化 + 新页面
10. **脚本**：4 个脚本
11. **文档**：更新 `docs/api_reference.md`、`README.md`

## 6. 验收

- [ ] `pytest -q` 全绿，覆盖率 ≥ 现有水平
- [ ] `cd frontend && npm run build` 0 错误
- [ ] `uvicorn app.main:app` 启动无报错；`/api/v1/health` 200
- [ ] design.md 目录树中所有列出文件均存在（或在计划中标注为"暂以 stub 实现"）
- [ ] 前端 5 个路由浅色一致、对话 SSE 可用
