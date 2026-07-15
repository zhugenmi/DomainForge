# DomainForge 后端 API 接口文档

> 版本：0.1.0 | 更新日期：2026-06-17 | Base URL: `/api/v1`

---

## 概览

所有接口前缀为 `/api/v1`，请求和响应均使用 JSON 格式。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/chat` | 发起对话 |
| GET | `/chat/stream` | SSE 流式对话 |
| POST | `/knowledge/index` | 导入文档到知识库（JSON 文本，兼容旧接口） |
| GET | `/knowledge/categories` | 列出所有知识类别 + 统计 |
| POST | `/knowledge/categories` | 创建用户自定义类别 |
| GET | `/knowledge/categories/{domain}/documents` | 列出某类别下的文档 |
| POST | `/knowledge/upload` | 两阶段导入步骤 1：上传→解析→切块→预览 |
| POST | `/knowledge/confirm` | 两阶段导入步骤 2：确认→embed→持久化 |
| DELETE | `/knowledge/documents/{id}` | 删除文档（级联删 chunks） |
| GET | `/knowledge/search` | 检索知识库（支持 hybrid/vector/bm25 三种模式） |
| GET | `/sessions` | 列出会话 |
| GET | `/sessions/{id}` | 获取会话详情 |
| GET | `/sessions/{id}/messages` | 获取会话消息列表 |
| DELETE | `/sessions/{id}` | 删除会话 |
| GET | `/audit` | 列出最近审计日志 |
| GET | `/audit/{trace_id}` | 按 trace_id 查询审计链路 |
| POST | `/evals/run` | 运行评测数据集 |
| GET | `/evals/results` | 列出评测结果 |
| GET | `/admin/tools` | 列出所有注册工具 |
| GET | `/admin/metrics` | 获取运行时指标快照 |
| GET | `/admin/health/detail` | 管理员可见的健康详情 |
| POST | `/auth/login` | 登录获取 JWT |
| GET | `/auth/me` | 获取当前用户 |
| GET | `/auth/admin-only` | 仅管理员可访问示例 |

---

## 健康检查

### `GET /api/v1/health`

检查服务是否运行。

**请求示例：**

```bash
curl http://localhost:8000/api/v1/health
```

**响应：**

```json
{
  "status": "ok"
}
```

---

## 对话

### `POST /api/v1/chat`

发起一次对话。自动识别意图、检索记忆和知识库、调用工具，返回最终答案。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户问题 |
| session_id | string (UUID) | 否 | 会话 ID，为空时自动创建新会话 |

**请求示例：**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是民法典？"}'
```

**续接会话：**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "能否详细说明？", "session_id": "550e8400-e29b-41d4-a716-446655440000"}'
```

**响应：**

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | string (UUID) | 会话 ID（新会话或已有会话） |
| answer | string | 最终答案 |
| intent | string \| null | 识别到的意图（chat / knowledge / tool） |

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "answer": "民法典是...",
  "intent": "knowledge"
}
```

---

### `GET /api/v1/chat/stream`

SSE 流式对话。逐步推送 Agent 执行过程中的中间状态和最终答案。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户问题 |
| session_id | string (UUID) | 否 | 会话 ID，为空时自动创建新会话 |

**请求示例：**

```bash
curl -N "http://localhost:8000/api/v1/chat/stream?query=你好"
```

**响应：**

Content-Type: `text/event-stream`

每个事件格式为 `data: {JSON}\n\n`，JSON 结构为：

| 字段 | 类型 | 说明 |
|------|------|------|
| event | string | 事件类型 |
| data | object | 事件数据 |

**SSE 事件类型：**

| 事件 | 说明 | data 字段 |
|------|------|-----------|
| `intent_detected` | 意图识别完成 | `intent: string` |
| `plan_generated` | 任务计划生成 | `plan: list` |
| `retrieval_started` | 知识库检索开始 | `query: string` |
| `tool_called` | 工具被调用 | `tool: string, args: dict` |
| `tool_result` | 工具执行结果 | `tool: string, result: any` |
| `reflection` | 反思评估 | `assessment: string` |
| `final_answer` | 最终答案 | `answer: string` |
| `error` | 错误信息 | `message: string` |

**流式响应示例：**

```
data: {"event": "intent_detected", "data": {"status": "recognizing"}}

data: {"event": "intent_detected", "data": {"intent": "chat"}}

data: {"event": "final_answer", "data": {"answer": "你好！有什么可以帮助你的？"}}
```

**前端接入示例（JavaScript）：**

```javascript
const eventSource = new EventSource('/api/v1/chat/stream?query=你好');
eventSource.onmessage = (event) => {
  const { event: type, data } = JSON.parse(event.data);
  if (type === 'final_answer') {
    console.log('答案:', data.answer);
    eventSource.close();
  } else if (type === 'error') {
    console.error('错误:', data.message);
    eventSource.close();
  } else {
    console.log(`[${type}]`, data);
  }
};
```

---

## 知识库

### `POST /api/v1/knowledge/index`

导入文档到知识库。自动分块、生成 embedding、存储到向量数据库。

**请求体：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| domain | string | 是 | 领域标签（如 legal, finance） |
| title | string | 是 | 文档标题 |
| content | string | 是 | 文档正文内容 |
| source | string | 否 | 来源标识（文件名、URL 等） |

**请求示例：**

```bash
curl -X POST http://localhost:8000/api/v1/knowledge/index \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "legal",
    "title": "民法典总则编",
    "content": "第一条 为了保护民事主体的合法权益……",
    "source": "民法典.pdf"
  }'
```

**响应：**

| 字段 | 类型 | 说明 |
|------|------|------|
| document_id | string (UUID) | 文档 ID |
| chunks | integer | 分块数量 |

```json
{
  "document_id": "660e8400-e29b-41d4-a716-446655440001",
  "chunks": 12
}
```

**分块策略：** 默认按段落 + 句子边界做语义分块（`chunk_size=500`，`overlap=50`）；当 `domain=legal` 时按"第X条"切分（保留条号），`domain=finance` 时按标题层级切分。可在 `app/rag/chunk/` 下扩展更多领域分块器。

---

### `GET /api/v1/knowledge/search`

检索知识库，返回与查询语义最相关的文档片段。

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| query | string | 是 | — | 检索查询文本 |
| top_k | integer | 否 | 5 | 返回结果数量 |
| mode | string | 否 | hybrid | 检索模式：`hybrid` / `vector` / `bm25` |

**请求示例：**

```bash
curl "http://localhost:8000/api/v1/knowledge/search?query=合同效力&top_k=3"
```

**响应：**

| 字段 | 类型 | 说明 |
|------|------|------|
| results | list[ChunkResult] | 检索结果列表 |

**ChunkResult：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string (UUID) | 分块 ID |
| document_id | string (UUID) | 所属文档 ID |
| content | string | 分块文本内容 |
| metadata | object | 元数据（领域、chunk_index、article/heading 等） |
| score | float | 综合排序分数（hybrid 模式为 RRF 融合后经过 rerank 的分数；vector/bm25 为各自的相似度/词频分数） |

```json
{
  "results": [
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "document_id": "660e8400-e29b-41d4-a716-446655440001",
      "content": "第一百四十三条 具备下列条件的民事法律行为有效……",
      "metadata": {
        "domain": "legal",
        "chunk_index": 5,
        "article": "第一百四十三条"
      },
      "score": 0.872
    }
  ]
}
```

> `mode=hybrid` 时先并行执行 BM25 与向量检索，再用 RRF 融合两路结果，最后经 BGE Reranker 重排取 top_k。

---

### `GET /api/v1/knowledge/categories`

列出所有知识类别（内置 + 用户自建），含文件数、字数、最近更新统计。

**响应：**

```json
{
  "categories": [
    {"name": "legal", "is_builtin": true, "document_count": 12, "word_count": 52300, "updated_at": "2026-06-17T08:00:00Z"}
  ]
}
```

内置类别：`legal`、`finance`、`medical`、`insurance`、`enterprise`。

---

### `POST /api/v1/knowledge/categories`

创建用户自定义类别。

**请求体：** `{"name": "hr_policy"}` · **响应：** `{"name": "hr_policy", "is_builtin": false}` · 409 if 已存在。

---

### `GET /api/v1/knowledge/categories/{domain}/documents`

列出指定类别下的文档（id / title / source / file_type / file_size_bytes / word_count / chunk_count / status / created_at / updated_at）。

---

### `POST /api/v1/knowledge/upload`  — Phase 2 两阶段导入：步骤 1

多文件上传 → 后端解析 + 切块 → 返回预览（**不 embed、不落库**），存入 `PreviewStore`（TTL `PREVIEW_SESSION_TTL=600s`）。

**Content-Type:** `multipart/form-data`

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| files | File[] | — | 必填，1–10 个文件，单文件 ≤20MB |
| domain | string | — | 必填，目标类别 |
| chunk_strategy | string | "semantic" | semantic / legal / finance |
| chunk_size | int | 500 | 仅 semantic 生效 |
| chunk_overlap | int | 50 | 仅 semantic 生效 |

**响应：** `PreviewSession`（含 `session_id`、`expires_in`、每文件 `filename`/`file_type`/`file_size_bytes`/`char_count`/`word_count`/`chunk_count`/`sample_chunks`）。

**错误码：** 400 文件数超限/无文件 · 404 类别不存在 · 413 单文件超 20MB。

---

### `POST /api/v1/knowledge/confirm`  — Phase 2 两阶段导入：步骤 2

用户确认预览后触发 embed + 持久化。

**请求体：** `{"session_id": "uuid"}` · **响应：** `{"document_ids": ["uuid", ...], "total_chunks": N}` · 410 preview session 过期或不存在。

设计动机：embed 是远程 API 调用、有成本且不可预览，让用户先看分块效果再决定入库。

---

### `DELETE /api/v1/knowledge/documents/{document_id}`

删除文档（级联清理其所有 chunks）。**响应：** `{"deleted": "uuid"}` · 404 if 不存在。

---

## 错误处理

所有接口在出错时返回 HTTP 4xx/5xx 状态码，响应体格式：

```json
{
  "detail": "错误描述信息"
}
```

常见错误：

| 状态码 | 场景 |
|--------|------|
| 422 | 请求参数校验失败（缺少必填字段、类型错误） |
| 500 | 服务内部错误（LLM 调用失败、数据库异常） |

---

## 内置工具

当前注册的工具，可被 Agent 自动调用，也可通过 `/admin/tools` 查看：

| 工具名 | 说明 | 权限 |
|--------|------|------|
| `knowledge_search` | 搜索知识库文档 | read |
| `calculator` | 数学表达式计算（白名单字符） | default |
| `web_search` | DuckDuckGo 网络搜索 | default |
| `sql_query` | 只读 SELECT SQL 执行器 | sensitive |
| `file_read` | 沙箱目录文件读取 | read |
| `file_write` | 沙箱目录文件写入 | sensitive |

工具通过 OpenAI function-calling 协议由 LLM 自动选择和调用。敏感权限的工具在生产环境应配置二次确认。

---

## 会话管理

### `GET /api/v1/sessions`

列出最近会话。

**查询参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| user_id | UUID | 可选，按用户过滤 |
| limit | int | 默认 50 |

### `GET /api/v1/sessions/{session_id}/messages`

返回会话内消息（按时间升序）。

---

## 审计日志

### `GET /api/v1/audit/{trace_id}`

按 trace_id 返回完整审计链路。trace_id 在 `/chat` 与 `/chat/stream` 调用过程中由后端生成。

### `GET /api/v1/audit?limit=50`

返回最近审计条目。

---

## 评测

### `POST /api/v1/evals/run`

执行指定评测集，返回每个用例的指标。

**请求体：**

```json
{ "dataset": "legal/legal_basic" }
```

内置数据集：`legal/legal_basic`、`finance/finance_basic`。

### `GET /api/v1/evals/results?dataset=...`

列出评测结果。

---

## 管理后台

### `GET /api/v1/admin/tools`

返回所有内置工具的 schema。

### `GET /api/v1/admin/metrics`

返回进程内计数器与计时器快照。

### `GET /api/v1/admin/health/detail`

需要 admin 角色（dev 模式默认放行）。返回健康状态、metrics、当前用户。

---

## 认证

### `POST /api/v1/auth/login`

dev 环境下任意用户名可登录，密码为 `ADMIN_API_KEY` 时颁发 admin 角色。

```json
{ "username": "alice", "password": "" }
```

返回：

```json
{ "access_token": "eyJ...", "token_type": "bearer", "role": "user" }
```

### `GET /api/v1/auth/me`

返回当前用户身份。dev 模式无 token 时返回默认 admin 身份；生产环境需在 `Authorization: Bearer <token>` 中携带 JWT。

---

## 交互式文档

启动服务后，访问以下地址查看自动生成的 Swagger UI：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
