# 修复：让 Agent 据实回答"有哪些知识库 / 有哪些技能"

> 日期：2026-06-27
> 类型：行为修复（非崩溃性 bug，但严重损害回答可信度）
> 影响范围：`/api/v1/chat` 与 `/chat/stream` 主回答链路

## 1. 问题现象

用户在对话中问：

- "当前有哪些知识库？"
- "你目前安装了哪些 skills？"

助手回答的全是 **RAG 通用概念**（"企业文档 / 网站内容 / 数据库 / FAQ…"），而不是系统里实际配置的类别；问 skills 时回答"没有安装额外技能模块"。两个问题都没有基于系统真实状态作答。

## 2. 根因分析

三层叠加，核心是**模型根本不知道系统里有什么，也没有任何手段去查**。

### 2.1 意图分类把元问题路由成 `chat`

`app/runtime/nodes/intent_node.py` 的意图体系只有三类：`chat / knowledge / tool`。

- "当前有哪些知识库？" 不是在检索某条知识，意图器大概率判为 `chat`。
- 即便误判为 `knowledge`，`RetrievalNode.execute` 也只是对文档片段做语义检索，对"有哪些库"这种**元问题**完全无效——它返回的是片段，不是目录。

### 2.2 没有"列出知识库目录"的能力

`KnowledgeTool`（`app/tools/builtin/knowledge_tool.py`）只会 `rag_service.search(query)` 返回文档片段。系统里有 `categories` 表和 `DocumentRepo.get_stats_by_domain()` 聚合查询（`/api/v1/knowledge/categories` 端点已经在用），但**这个能力没暴露给 Agent**。LLM 无法枚举知识库类别、文档域、文档数量，只能凭训练知识编一份通用清单。

### 2.3 AnswerNode 系统 prompt 没注入任何系统能力上下文

修复前 `app/runtime/nodes/answer_node.py` 的系统 prompt：

```
你是一个专业的领域助手。请根据以下信息回答用户问题。
{context}
```

`context` 只拼了 对话历史 / 检索片段 / 工具结果，**没有注入"当前已注册知识库目录"和"可用工具列表"**。模型既不知道有哪些 KB，也不知道自己有哪些 tools。

### 2.4 "skills" 在系统里根本不存在

DomainForge 的能力单元叫 **tools**（`tool_registry`），不叫 skills。注册到 chat 的有 `knowledge_search / calculator / search / file_read / file_write`。`tool_registry.list_tools()` 方法存在但**从没被注入 prompt**，所以 LLM 无法回答"你有哪些技能"。

## 3. 解决方案

按 P0 两项落地（最小可行修复）：哪怕意图还是 `chat`，只要 AnswerNode 的 system prompt 注入了真实的能力清单，模型就能据实回答。

### 3.1 新增 `ListKnowledgeBasesTool`

`app/tools/builtin/knowledge_catalog_tool.py`

- 复用现有 `CategoryRepo.list_all()` + `DocumentRepo.get_stats_by_domain()`，返回 `[{name, is_builtin, file_count, word_count, last_updated}]`。
- 无参数工具，`permission_scope="read"`，`timeout=5.0`。
- 在 `_build_runtime` 注册（`app/api/chat.py`）。

设计选择：直接复用 `/api/v1/knowledge/categories` 端点同款查询逻辑，避免目录口径分裂。

### 3.2 AnswerNode 注入系统能力上下文

`app/runtime/nodes/answer_node.py`

- `AnswerNode` 新增 `tool_registry: ToolRegistry | None` 参数（默认 None，向后兼容现有测试中的 mock 节点）。
- 新增 `_build_capability_context()`：在每次回答前组装两段
  1. **知识库目录**：调用 `tool_registry.get("list_knowledge_bases").execute()`，渲染成 `- {name}（内置）: 文档 N 篇, 约 M 字`。
  2. **工具清单**：`tool_registry.list_tools()` 渲染成 `- {name}: {description}`。
- 任何子查询失败（如 DB 异常）降级为跳过该段，不影响主回答。
- `AgentRuntime._build_router` 把 `tool_registry` 传给 `AnswerNode`（`app/runtime/runtime.py`）。

注入位置在 `context_parts` 最前面，先于对话历史 / 检索片段 / 工具结果。

### 3.3 不在本次做的事

- **不新增 `meta` 意图类别**：P0 已能让 `chat` 意图下的元问题得到正确回答，引入新意图会牵动 Router 策略与测试，性价比不高。留作 P1。
- **不缓存能力上下文**：`categories` 聚合是轻量查询，每次回答实时拉取可保证目录新鲜；按 CLAUDE.md "No speculative" 原则不引入缓存。
- **不注册 `sql_tool`**：与本次问题无关，单独处理。

## 4. 改动清单

| 文件 | 改动 |
|---|---|
| `app/tools/builtin/knowledge_catalog_tool.py` | 新增 `ListKnowledgeBasesTool` |
| `app/api/chat.py` | `_build_runtime` 注册 `ListKnowledgeBasesTool(db=db)` |
| `app/runtime/nodes/answer_node.py` | 新增 `tool_registry` 参数与 `_build_capability_context()`，注入知识库目录 + 工具清单 |
| `app/runtime/runtime.py` | `_build_router` 向 `AnswerNode` 传 `tool_registry` |
| `tests/tools/test_knowledge_catalog_tool.py` | 新增 3 个测试：有数据 / 空库 / 类别无文档 |
| `tests/runtime/test_answer_node_capability.py` | 新增 3 个测试：注入校验 / 无 registry 兼容 / catalog 失败降级 |

## 5. 验证

- `pytest` 全量：**184 passed**（基线 178 + 新增 6），无回归。
- 手测路径（需先执行 `alembic upgrade head` 修复 `users.password_hash` 列缺失后）：
  - `GET /api/v1/chat/stream?query=当前有哪些知识库？` —— 回答应列出实际类别与文档数。
  - `GET /api/v1/chat/stream?query=你有哪些技能？` —— 回答应列出 `knowledge_search / list_knowledge_bases / calculator / search / file_read / file_write`。

## 6. 后续方向（P1/P2）

- **P1**：`IntentNode` 增加第 4 类 `meta` 意图（关键词："有哪些 / 列出 / 当前"），路由到工具节点调 `list_knowledge_bases`，让元问题走工具链而非纯 prompt 注入。
- **P2**：`sql_tool` 在 `_build_runtime` 的注册状态与 `tests/tools/test_builtin_tools.py` 不一致，需统一（注册或删死代码）。
- **P2**：能力上下文目前每次回答都查 DB，若后续 QPS 上升可考虑进程内短 TTL 缓存（如 30s），并在 `categories` / `documents` 写入时主动失效。
