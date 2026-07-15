# 06 自定义 Agent 模块：CRUD + 会话绑定 + Runtime 注入

> 版本：0.1.0 | 日期：2026-06-27 | 对应代码：`app/api/agents.py`、`app/database/models/agent.py`、`app/database/repositories/agent_repo.py`、`app/api/chat.py`、`app/runtime/state/agent_state.py`、`app/runtime/nodes/{retrieval,answer}_node.py`、`alembic/versions/0005_agents.py`

---

## 1. 设计目标

让用户可创建/编辑/删除智能体,配置名称、简介、system prompt、模型、温度、绑定知识库;会话可绑定 agent,对话时按 agent 配置注入 system prompt、domain 过滤、模型参数。系统默认 seed 一个法律咨询 builtin agent(绑定 `legal` 知识库)。

### 1.1 数据流

```
用户在 ChatWorkspace 顶栏选择 agent
    ↓
POST /chat { agent_id } 或 session.agent_id 兜底
    ↓
_resolve_agent: 解析生效 agent(request > session > None)
    ↓
_llm_for_agent: 用 agent.model_name 构造 LLM(构造时配置)
    ↓
_apply_agent_to_state: 把 system_prompt + domain 放进 AgentState(运行时配置)
    ↓
RetrievalNode: rag_service.search(query, domain=state.agent_domain)
AnswerNode: 用 state.agent_system_prompt 替换默认 prompt
```

### 1.2 配置分层

agent 配置分两类,注入路径不同:

| 配置 | 类型 | 注入点 |
|---|---|---|
| `model_name` / `temperature` | 构造时 | `_llm_for_agent` 构造 `FallbackPolicy` 时设置 `provider.model` |
| `system_prompt` / `domain` | 运行时 | `AgentState` 字段,节点从 state 读 |

`model_name` 允许空字符串--空表示"跟随系统配置",运行时由 `_llm_for_agent` 解析为 `settings.DEFAULT_LLM_MODEL`。builtin 法律咨询 agent 即用此机制,避免把模型名硬编码进 migration 导致跨环境(OpenAI / DashScope / 本地)不可用。表单下拉的候选模型来自 `settings.AVAILABLE_MODELS`(逗号分隔,为空时回退 `[DEFAULT_LLM_MODEL]`),通过 `GET /agents/models` 暴露给前端。

`temperature` 当前未显式传入 `llm.generate(**kwargs)`--provider 用自身默认。后续若需精细控制,可在 `_llm_for_agent` 返回的 FallbackPolicy 上包装 `generate` 注入 kwargs,或在 AnswerNode/IntentNode 调用时传入。

---

## 2. 数据模型

### 2.1 `agents` 表

```python
class Agent(Base):
    __tablename__ = "agents"
    id: UUID PK
    name: String(100), unique, not null       # 显示名
    description: String(500), not null, ""     # 简介
    system_prompt: Text, not null, ""          # 说明 -> AnswerNode system prompt
    model_name: String(100), not null, ""      # 空=跟随 settings.DEFAULT_LLM_MODEL
    temperature: Float, not null, 0.7
    domain: String(50), nullable               # 绑定的 category name
    is_builtin: Boolean, false                 # builtin 不可删
    created_at / updated_at: DateTime
```

### 2.2 `sessions.agent_id`

nullable FK -> `agents.id`,`ondelete="SET NULL"`:删除 agent 后会话保留但 agent_id 置空,向后兼容。

### 2.3 Migration

`alembic/versions/0005_agents.py`:
- `down_revision = "0004_user_password_hash"`
- 建 `agents` 表 + `sessions.agent_id` 列
- seed 法律咨询 builtin:`name='法律咨询'`, `domain='legal'`, `model_name=''`(空,运行时跟随 `DEFAULT_LLM_MODEL`), `temperature=0.3`,system prompt 内联在 migration 中(法律顾问人设 + 不编造法条/不替代正式法律意见的约束)。

`alembic/versions/0006_legal_agent_default_model.py`:
- `down_revision = "0005_agents"`
- 把已 seed 的法律咨询 agent 的 `model_name` 从早期硬编码的 `'gpt-4o-mini'` 重置为空字符串。早期 0005 版本曾硬编码模型名,跨 LLM 网关(OpenAI / DashScope 等)会 404;0005 已修正 seed,0006 修补已部署环境。

> **注意**:测试用 sqlite 内存库走 `Base.metadata.create_all`,不跑 alembic,故 seed 仅服务生产 Postgres。测试 fixture 自行插入所需 agent 行。

---

## 3. API

### 3.1 `/agents` CRUD

| Method | Path | 行为 |
|---|---|---|
| GET | `/agents` | 列表(builtin + custom) |
| GET | `/agents/models` | 返回配置中可用模型列表(`settings.AVAILABLE_MODELS`,为空回退 `[DEFAULT_LLM_MODEL]`) |
| GET | `/agents/{id}` | 详情 |
| POST | `/agents` | 创建;强制 `is_builtin=false`;校验 domain 存在(404) |
| PUT | `/agents/{id}` | 更新;schema 拒绝 `is_builtin` 翻转(422);校验 domain;名称冲突(409) |
| DELETE | `/agents/{id}` | 删除;builtin 返回 403 |

`model_name` 在 `AgentCreate`/`AgentUpdate` 中允许空字符串(语义"跟随系统配置"),schema 不强制 `min_length=1`。

### 3.2 会话绑定

- `POST /sessions` body `{ agent_id?: uuid }`:创建时绑定。
- `PUT /sessions/{id}` body `{ agent_id?: uuid }`:切换 agent。前端顶栏下拉用此接口。
- `GET /sessions` / `GET /sessions/{id}` 返回 `agent_id` 字段。

### 3.3 Chat 注入

`POST /chat` 的 `ChatRequest` 增加可选 `agent_id`。优先级:`request.agent_id` > `session.agent_id` > None。流式 `GET /chat/stream` 当前签名不接 `agent_id`,沿用 session 绑定的 agent。

---

## 4. Runtime 注入细节

### 4.1 AgentState 扩展

```python
agent_system_prompt: str = ""
agent_domain: str | None = None
```

默认空值 -> 走原默认行为,现有测试不受影响。

### 4.2 RetrievalNode

```python
chunks = await self.rag_service.search(state.query, domain=state.agent_domain)
```

`domain=None` 时 RAGService 跨所有域检索(原行为);`domain="legal"` 时仅检索 legal 域文档。

> **关键修复**:领域 agent 绑定后,`agent_domain` 非空时**强制触发检索**,不再依赖 `intent == "knowledge"`。详见 [fix/2026-06-27-domain-agent-retrieval-skipped.md](../fix/2026-06-27-domain-agent-retrieval-skipped.md)。

### 4.3 AnswerNode

```python
base_prompt = state.agent_system_prompt if state.agent_system_prompt else ANSWER_SYSTEM_PROMPT
if "{context}" in base_prompt:
    system_prompt = base_prompt.format(context=context)
else:
    system_prompt = f"{base_prompt}\n\n参考信息:\n{context}"
```

兼容两种 prompt 风格:含 `{context}` 占位符的模板格式化;否则追加参考信息块。法律咨询 seed 的 prompt 不含 `{context}`,走追加分支。

### 4.4 `_llm_for_agent`

```python
provider = router.get_provider()
model = agent.model_name or settings.DEFAULT_LLM_MODEL
if model:
    provider.model = model
return FallbackPolicy(primary=provider, secondary=...)
```

`agent.model_name` 为空 -> 回退 `settings.DEFAULT_LLM_MODEL`,使 builtin agent 跨环境可用。agent 为 None -> `router.get_fallback()`(原行为)。构造失败 -> log warning + fallback,不阻断对话。

---

## 5. 配置项

| 环境变量 | 说明 | 默认 |
|---|---|---|
| `AVAILABLE_MODELS` | agent 表单下拉的可用模型列表(逗号分隔);为空回退 `[DEFAULT_LLM_MODEL]` | `""` |
| `DEFAULT_LLM_MODEL` | agent `model_name` 为空时回退用的默认模型 | `gpt-4o` |

部署时在 `.env` 设置 `AVAILABLE_MODELS=deepseek-v4-pro,...` 列出网关实际可用的模型。

---

## 6. 当前限制与后续

1. **金融问答 builtin agent seed**:数据模型与 API 已预留,待加一行 migration seed(`domain='finance'`)。
2. **temperature 注入**:当前 `agent.temperature` 存储但未传入 `llm.generate`。需在 FallbackPolicy 层包装或节点调用时传 kwargs。详见 [fix/2026-06-27-domain-agent-retrieval-skipped.md](../fix/2026-06-27-domain-agent-retrieval-skipped.md) §6 后续。
3. **流式 agent_id 覆盖**:`chat_stream` 签名加 `agent_id` query param,支持 request 级覆盖。
4. **一对多知识库**:当前 1:1 绑定;若需 agent 绑多域,改 `domain` 为数组并在 RetrievalNode 传 `domain__in`。
5. **agent 级工具集**:当前所有 agent 共享全局 tool registry;若需按 agent 启用/禁用工具,加 `agent.tools` 关联表。
6. **Domain 漂移告警**:agent 绑定的 category 被删时,当前静默降级为空检索;可加启动校验或 admin 告警。
