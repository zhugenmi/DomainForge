# DomainForge 文档门户

> 本目录是项目所有技术文档的入口。先读本 README 选路,再深入对应文档。

## 边界声明(每个目录的归属规则)

| 目录 | 归属规则 | 不属于这里 |
|---|---|---|
| `architecture/` | 系统"如何运行"的当前架构(as-built):模块划分、运行机制、技术栈表、接口契约、已知限制 | "为什么选 X" -> `adr/`;bug 修复 -> `fix/` |
| `adr/` | 架构决策记录:"为什么选 X 而非 Y",含备选方案与拒绝原因 | 当前架构描述 -> `architecture/` |
| `fix/` | 已解决的工程问题:代码 bug、性能回归、集成故障、生产事故,含根因分析 + 验证 + 复盘 | 模型输出质量问题 -> `eval/`;未实现的想法 -> `architecture/` §限制 |
| `eval/` | 评测报告:检索质量、运行时性能、模型质量,含方法 + 数据 + 量化结论 | 日常 metrics -> `architecture/05` |
| `plan/` | 设计源头与路线图:`design.md`(架构源头) + `full-implementation.md`(实现计划) | 实现细节 -> `architecture/` |
| `api_reference.md` | 端点级请求/响应契约 | 架构原理 -> `architecture/` |

## 目录树

```
docs/
├── README.md                 # 本文件(导航枢纽)
├── api_reference.md          # API 端点契约(18+ 端点)
├── architecture/             # 当前架构(按能力域分篇)
│   ├── README.md
│   ├── 01_orchestration_engine.md   # Agent Runtime:State+Node+Router+SSE
│   ├── 02_model_capability.md       # LLM Provider + Tool Registry + MCP
│   ├── 03_enhanced_rag.md           # 检索:BM25+向量+RRF+Rerank+引用
│   ├── 04_backend_service.md        # RESTful+SSE+Redis+安全层
│   ├── 05_observability_evals.md    # OTel Tracing+Metrics+Evals
│   ├── 06_agents.md                 # 自定义 Agent 模块
│   └── 07_skills.md                 # Skill 管理模块(可插拔指令包)
├── adr/                      # 架构决策记录
│   ├── 0001-pgvector-over-chroma.md
│   ├── 0002-openai-compatible-providers.md
│   ├── 0003-pbkdf2-over-bcrypt.md
│   ├── 0004-async-import-over-sync.md
│   ├── 0005-skill-as-instruction-not-tool.md
│   └── 0006-llmprovider-default-not-implemented.md
├── fix/                      # Bug 修复与问题解决(按日期排序)
│   ├── 2026-06-17-sqlite-jsonb-pgvector-compat.md
│   ├── 2026-06-17-tool-registry-duplicate-register.md
│   ├── 2026-06-27-agent-capability-visibility.md
│   ├── 2026-06-27-citation-chapter-missing.md
│   ├── 2026-06-27-domain-agent-retrieval-skipped.md
│   ├── 2026-06-27-rerank-not-effective.md
│   ├── 2026-06-28-citation-reorder-locator.md
│   ├── 2026-06-28-confirm-session-duplicate-consume.md
│   ├── 2026-06-28-embedding-429-dimension-mismatch.md
│   ├── 2026-06-28-skill-path-traversal.md
│   └── 2026-06-28-stream-cancel-and-test-pollution.md
├── eval/                     # 评测报告
│   ├── 2026-06-30-rag-retrieval-quality.md
│   └── 2026-07-01-runtime-performance.md
└── plan/                     # 设计源头与路线图
    ├── design.md             # 项目原始设计稿(架构源头)
    └── full-implementation.md # 全量实现计划与进度
```

## 按场景导航

### 我是新成员,想理解系统怎么运行

1. [plan/design.md](plan/design.md) - 项目原始设计稿,五层架构 + 四阶段执行框架 + 数据库设计
2. [architecture/01_orchestration_engine.md](architecture/01_orchestration_engine.md) - Agent Runtime 核心:State + Node + Router + 四阶段(Planning/Memory/Tool/Reflection)
3. [architecture/04_backend_service.md](architecture/04_backend_service.md) - 后端服务:RESTful API + SSE 流式 + Redis + 安全层
4. [architecture/03_enhanced_rag.md](architecture/03_enhanced_rag.md) - 检索管线:双路召回 + RRF + Rerank + 引用
5. [architecture/02_model_capability.md](architecture/02_model_capability.md) - 能力层:多 Provider + Tool Registry + MCP
6. [architecture/05_observability_evals.md](architecture/05_observability_evals.md) - 可观测性:OTel Tracing + Metrics + Evals
7. [architecture/06_agents.md](architecture/06_agents.md) / [architecture/07_skills.md](architecture/07_skills.md) - 扩展模块

### 我在排查 bug / 线上问题

1. 先看 [architecture/05_observability_evals.md](architecture/05_observability_evals.md) §6 可观测性全景,理解 trace_id 如何串链路
2. 按 trace_id 查 `audit_logs` 表或 Jaeger
3. 对照 [fix/](fix/) 目录,按日期倒序看是否有同类问题已解决
4. 重点案例:
   - 流式响应 cancel 导致消息丢失:[fix/2026-06-28-stream-cancel-and-test-pollution.md](fix/2026-06-28-stream-cancel-and-test-pollution.md)
   - 领域 agent 检索被跳过:[fix/2026-06-27-domain-agent-retrieval-skipped.md](fix/2026-06-27-domain-agent-retrieval-skipped.md)
   - Embedding 429 + 维度不匹配:[fix/2026-06-28-embedding-429-dimension-mismatch.md](fix/2026-06-28-embedding-429-dimension-mismatch.md)
   - Rerank 静默失效(三 bug 叠加):[fix/2026-06-27-rerank-not-effective.md](fix/2026-06-27-rerank-not-effective.md)

### 我想了解某项技术选型为什么

见 [adr/](adr/) 目录:

- 向量库为什么用 pgvector:[adr/0001](adr/0001-pgvector-over-chroma.md)
- LLM Provider 为什么都走 OpenAI 兼容:[adr/0002](adr/0002-openai-compatible-providers.md)
- 密码哈希为什么用 PBKDF2 而非 bcrypt:[adr/0003](adr/0003-pbkdf2-over-bcrypt.md)
- 知识库导入为什么用异步任务:[adr/0004](adr/0004-async-import-over-sync.md)
- Skill 为什么是指令包而非 tool:[adr/0005](adr/0005-skill-as-instruction-not-tool.md)
- `chat_with_tools` 为什么默认抛错而非 abstract:[adr/0006](adr/0006-llmprovider-default-not-implemented.md)

### 我想看检索质量 / 性能基线

- RAG 检索质量评测(Recall/MRR/NDCG):[eval/2026-06-30-rag-retrieval-quality.md](eval/2026-06-30-rag-retrieval-quality.md)
- 运行时性能基线(延迟 p50/p99 + Token 成本):[eval/2026-07-01-runtime-performance.md](eval/2026-07-01-runtime-performance.md)

### 我要重构 / 改动某个模块

1. 先读对应 `architecture/0X_*.md` 末尾的"当前限制"章节,避免重复踩坑
2. 检查 [fix/](fix/) 是否有相关历史问题的复盘
3. 大改动先看 [adr/](adr/) 确认决策上下文是否仍成立

### 我要接手未完成工作

1. [plan/full-implementation.md](plan/full-implementation.md) - 看整体进度
2. 各 `architecture/0X_*.md` 的"当前限制与后续"章节 - 看具体 gap
3. 各 `fix/2026-*.md` 的"复盘"章节 - 看可复用的教训

## 阅读顺序建议

- **新成员**:`plan/design.md` -> `architecture/01` -> `04` -> `03` -> `02` -> `05` -> `06` -> `07`
- **排查问题**:`architecture/05`(看 trace/metrics) -> `01`(看节点链路) -> 对应能力域文档 -> `fix/`(找同类案例)
- **重构前**:先读对应篇的"当前限制"章节,避免重复踩坑
- **接手未完成工作**:`plan/full-implementation.md` 看 gap 列表 -> 对应 `architecture/0X_*.md` 看模块设计 -> `fix/` 看历史教训

## 文档维护约定

1. **架构文档如实区分已实现与规划**:避免"用将来时描述已存在的能力";限制章节标注"已解除/部分解除/未解决"。
2. **代码与文档同步**:每次合入破坏性改动时,同步更新对应 `architecture/0X_*.md`;新增模块新建 arch 文档。
3. **bug 修复必写 fix 记录**:非平凡问题(根因非显然)解决后,在 `fix/` 新建 `YYYY-MM-DD-slug.md`,含根因分析 + 验证 + 复盘。
4. **技术选型必写 ADR**:有"为什么选 X 而非 Y"的决策,在 `adr/` 新建 `00XX-slug.md`,含备选方案与拒绝原因。
5. **评测报告归 eval**:检索质量、性能基线、模型质量评测,在 `eval/` 新建 `YYYY-MM-DD-slug.md`,含方法 + 数据 + 量化结论。
6. **日期前缀**:fix/eval 用 `YYYY-MM-DD-slug.md`,日期从文档正文提取(无则用文件 mtime);ADR 用 `00XX-slug.md` 顺序编号。
