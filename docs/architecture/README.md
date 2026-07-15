# DomainForge 架构文档

> 本目录是项目的当前架构权威文档,按能力域分篇。每篇文档"如实区分已实现与规划",避免与代码脱节。

## 文档索引

| # | 文档 | 覆盖能力 | 关键模块 |
|---|------|---------|---------|
| 01 | [编排引擎设计](01_orchestration_engine.md) | Agent Runtime | State + Node + Router;Planning/Memory/Tool/Reflection 四阶段;ReAct + Plan&Execute 混合;SSE 流式;并行节点 |
| 02 | [模型与能力层](02_model_capability.md) | LLM + Tool + MCP | 多 Provider 封装;ModelRouter 动态路由与 Fallback 降级;`chat_with_tools` 抽象;Tool Registry;MCP 适配器;敏感工具二次确认 |
| 03 | [增强检索](03_enhanced_rag.md) | RAG 子系统 | PostgreSQL + pgvector;BM25 + 向量 + RRF + Rerank;领域分块;Query 改写;引用增强;异步导入 |
| 04 | [后端服务架构](04_backend_service.md) | HTTP + Redis + 安全 | RESTful API;SSE 流式;Redis 缓存/限流/共享 session;JWT + RBAC + PBKDF2 密码;优雅关机 |
| 05 | [可观测性与评测](05_observability_evals.md) | Tracing + Metrics + Evals | OTel SDK Tracing(已接入);Metrics 双写;Evals 启发式 + LLM-as-judge;Bad Case 闭环 |
| 06 | [自定义 Agent 模块](06_agents.md) | Agent CRUD + 会话绑定 | agents 表;session.agent_id;Runtime 注入 system_prompt + domain;builtin 法律咨询 agent |
| 07 | [Skill 管理模块](07_skills.md) | 可插拔指令包 | SKILL.md 规范;SkillRegistry;A1 始终注入;MarketplaceAdapter;installed_skills 持久化 |

## 配套文档

- [API 接口参考](../api_reference.md) - 端点级请求/响应契约(18+ 端点)
- [架构决策记录(ADR)](../adr/) - "为什么选 X 而非 Y"的决策记录
- [Bug 修复记录](../fix/) - 已解决工程问题的根因分析 + 复盘
- [评测报告](../eval/) - 检索质量与运行时性能基线
- [项目设计稿](../plan/design.md) - 架构源头(`plan/design.md`)
- [实现计划](../plan/full-implementation.md) - 全量实现计划与进度

## 阅读顺序建议

- **新成员**:`plan/design.md` -> `01` -> `04` -> `03` -> `02` -> `05` -> `06` -> `07`
- **排查问题**:`05`(看 trace/metrics) -> `01`(看节点链路) -> 对应能力域文档 -> `fix/`(找同类案例)
- **重构前**:先读对应篇的"当前限制"章节,避免重复踩坑;大改动查 `adr/` 确认决策上下文
- **接手未完成工作**:各篇"当前限制与后续"章节标注了 gap 与已解除项

## 维护约定

1. **如实区分已实现与规划**:架构文档避免"用将来时描述已存在的能力";限制章节标注"已解除/部分解除/未解决"。
2. **代码与文档同步**:每次合入破坏性改动时,同步更新对应 `0X_*.md`;新增模块新建 arch 文档。
3. **限制章节要诚实**:已解决的 gap 标"已解除"并链接到 fix/adr;未解决的标"未解决"并说明影响。
