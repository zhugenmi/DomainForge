# 领域定制智能对话与知识服务平台

> 面向法律、金融、企业知识库等垂直领域场景构建的企业级 Agent 应用开发平台。
>  平台以 **自研 Agent Runtime** 为核心，集成 **任务规划（Planning）、记忆管理（Memory）、工具调用（Tool Use）、结果反思（Reflection）** 四阶段执行框架，实现多轮对话、知识检索、工具编排、会话记忆与安全审计能力，支持快速构建行业级 AI 助手。

---

## 1. 项目背景

传统大模型应用普遍存在以下问题：

- 无法完成复杂任务拆解
- 缺乏长期记忆能力
- 工具调用能力弱
- 检索结果不稳定
- 缺少审计与可观测能力
- 难以快速迁移到新行业场景

因此设计本项目，构建一套可扩展、可配置、可观测的 Agent Runtime 平台。目标是实现：

```
用户问题
    ↓
Agent理解任务
    ↓
规划执行步骤
    ↓
调用工具与知识库
    ↓
反思与纠错
    ↓
生成最终答案
```

适用场景包括：

- 法律咨询：法条检索、案例问答、条款对比、风险提示；
- 金融知识服务：产品解释、政策摘要、指标分析、研报问答；
- 企业内部知识助手：制度问答、流程指引、文档检索与归纳。

---

## 2. 核心能力

### Agent能力

- 多轮对话
- 意图识别
- 任务规划
- 工具调用
- 会话记忆
- 结果反思
- 错误恢复
- 流式输出

------

### RAG能力

- 文档解析
- 向量检索
- BM25全文检索
- Hybrid Search
- RRF融合
- CrossEncoder Rerank

------

### Tool能力

- Search Tool
- SQL Tool
- Knowledge Tool
- Document Tool
- MCP Tool

------

### 企业能力

- 用户管理
- 会话管理
- 权限控制
- 审计日志
- Tracing监控
- Evals评测

---

## 3. 总体架构

### 3.1 分层设计

系统建议划分为五层：

- **交互层**：Web / API / SSE 流式输出
- **编排层**：Agent Runtime、任务规划、状态机、反思与重试
- **能力层**：模型路由、Tool Calling、MCP 接入、内部 Skill/API
- **数据层**：知识库、会话、缓存、审计日志、评测集
- **可观测层**：Tracing、Monitoring、Error Tracking、Evals

### 3.2 逻辑架构图

```text
┌────────────────────────────────────┐
│            Frontend UI             │
│      Web / Admin / Dashboard       │
└────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│             FastAPI API            │
│      RESTful API + SSE Stream      │
└────────────────────────────────────┘
                 │
                 ▼

┌────────────────────────────────────┐
│           Agent Runtime            │
│                                    │
│  Planner                           │
│  Memory Manager                    │
│  Tool Executor                     │
│  Reflection Engine                 │
│  Router                            │
│  Event Bus                         │
└────────────────────────────────────┘

        │          │          │

        ▼          ▼          ▼

┌────────────┐ ┌────────────┐ ┌────────────┐
│ LLM Router │ │ Tool Hub   │ │ RAG Hub    │
└────────────┘ └────────────┘ └────────────┘

                 │

                 ▼

┌────────────────────────────────────┐
│      PostgreSQL + pgvector         │
│                                    │
│ users                              │
│ sessions                           │
│ messages                           │
│ documents                          │
│ document_chunks                    │
│ memories                           │
│ audit_logs                         │
│ eval_results                       │
└────────────────────────────────────┘

                 │

                 ▼

┌────────────────────────────────────┐
│         OpenTelemetry              │
│   Trace / Metrics / Monitoring     │
└────────────────────────────────────┘
```

---

## 4. 技术选型

| 模块          | 技术                               |
| ------------- | ---------------------------------- |
| 后端框架      | FastAPI                            |
| Agent Runtime | 自研（State + Node + Router 架构） |
| 数据库        | PostgreSQL                         |
| 向量检索      | pgvector                           |
| 缓存          | Redis                              |
| ORM           | SQLAlchemy                         |
| 向量模型      | BGE-M3                             |
| Rerank模型    | BGE-Reranker                       |
| 工具协议      | MCP                                |
| 可观测        | OpenTelemetry                      |
| 鉴权          | JWT                                |
| 前端          | Next.js                            |
| 容器化        | Docker                             |

---

## 5. 目录结构

建议采用如下目录结构：

```text
domainforge/
│
├── app/                                  # 核心应用代码
│
│   ├── api/                              # API接口层（FastAPI Router）
│   │   ├── chat.py                       # 对话接口
│   │   ├── knowledge.py                  # 知识库管理接口
│   │   ├── evals.py                      # 评测接口
│   │   ├── admin.py                      # 管理后台接口
│   │   └── health.py                     # 健康检查
│   │
│   ├── runtime/                          # Agent Runtime核心引擎
│   │
│   │   ├── state/                        # Agent状态管理
│   │   │   ├── agent_state.py            # Agent共享状态定义
│   │   │   └── state_manager.py          # 状态读写与生命周期管理
│   │   │
│   │   ├── planner/                      # 任务规划模块
│   │   │   ├── planner.py                # Planner主逻辑
│   │   │   ├── task_decomposer.py        # 任务拆解器
│   │   │   └── prompt.py                 # Planning Prompt模板
│   │   │
│   │   ├── router/                       # 流程路由器
│   │   │   ├── router.py                 # 节点调度逻辑
│   │   │   ├── condition.py              # 条件判断规则
│   │   │   └── strategy.py               # 路由策略
│   │   │
│   │   ├── nodes/                        # Runtime执行节点
│   │   │   ├── base.py                   # 节点基类
│   │   │   ├── intent_node.py            # 意图识别
│   │   │   ├── memory_node.py            # 记忆检索
│   │   │   ├── retrieval_node.py         # RAG检索
│   │   │   ├── tool_node.py              # 工具调用
│   │   │   ├── reflection_node.py        # 结果反思
│   │   │   └── answer_node.py            # 最终回答生成
│   │   │
│   │   ├── reflection/                   # Reflection机制
│   │   │   ├── evaluator.py              # 结果质量评估
│   │   │   ├── critic.py                 # 错误分析器
│   │   │   └── retry_policy.py           # 重试策略
│   │   │
│   │   ├── events/                       # Runtime事件总线
│   │   │   ├── event_bus.py              # 事件分发
│   │   │   ├── event_type.py             # 事件定义
│   │   │   └── publisher.py              # 事件发布器
│   │   │
│   │   └── runtime.py                    # Agent Runtime入口
│   │
│   ├── llm/                              # 大模型能力层
│   │
│   │   ├── providers/                    # 各模型Provider实现
│   │   │   ├── openai.py
│   │   │   ├── deepseek.py
│   │   │   ├── glm.py
│   │   │   ├── qwen.py
│   │   │   └── gemini.py
│   │   │
│   │   ├── router/                       # 模型路由与降级
│   │   │   ├── model_router.py
│   │   │   └── fallback.py
│   │   │
│   │   ├── embedding/                    # Embedding服务
│   │   │   ├── bge.py
│   │   │   └── embedding_service.py
│   │   │
│   │   ├── rerank/                       # Rerank服务
│   │   │   ├── bge_reranker.py
│   │   │   └── rerank_service.py
│   │   │
│   │   └── base.py                       # LLM统一抽象接口
│   │
│   ├── tools/                            # Tool Calling体系
│   │
│   │   ├── registry/                     # Tool注册中心
│   │   │   ├── registry.py
│   │   │   └── schema.py
│   │   │
│   │   ├── builtin/                      # 内置工具
│   │   │   ├── search_tool.py
│   │   │   ├── sql_tool.py
│   │   │   ├── file_tool.py
│   │   │   ├── knowledge_tool.py
│   │   │   └── calculator_tool.py
│   │   │
│   │   ├── mcp/                          # MCP协议适配层
│   │   │   ├── client.py                 # MCP Client
│   │   │   ├── filesystem.py             # 文件系统工具
│   │   │   ├── github.py                 # GitHub工具
│   │   │   └── browser.py                # 浏览器工具
│   │   │
│   │   └── base.py                       # Tool统一接口
│   │
│   ├── rag/                              # 检索增强系统
│   │
│   │   ├── parser/                       # 文档解析
│   │   │   ├── pdf_parser.py
│   │   │   ├── docx_parser.py
│   │   │   ├── markdown_parser.py
│   │   │   └── html_parser.py
│   │   │
│   │   ├── chunk/                        # 文本切块策略
│   │   │   ├── semantic_chunker.py
│   │   │   ├── legal_chunker.py
│   │   │   └── finance_chunker.py
│   │   │
│   │   ├── retrieval/                    # 检索算法
│   │   │   ├── bm25.py                   # 全文检索
│   │   │   ├── vector.py                 # 向量检索
│   │   │   ├── hybrid.py                 # 混合召回
│   │   │   └── rrf.py                    # RRF融合
│   │   │
│   │   ├── indexing/                     # 建库流程
│   │   │   ├── document_loader.py
│   │   │   ├── embedder.py
│   │   │   └── pipeline.py
│   │   │
│   │   ├── context/                      # 上下文构造
│   │   │   ├── builder.py
│   │   │   └── citation.py
│   │   │
│   │   └── service.py                    # RAG统一服务入口
│   │
│   ├── memory/                           # 记忆系统
│   │
│   │   ├── short_term/                   # 短期记忆
│   │   │   └── buffer_memory.py
│   │   │
│   │   ├── summary/                      # 摘要记忆
│   │   │   └── summary_memory.py
│   │   │
│   │   ├── long_term/                    # 长期记忆
│   │   │   └── vector_memory.py
│   │   │
│   │   ├── manager.py                    # 记忆调度器
│   │   └── memory_service.py             # 记忆服务
│   │
│   ├── database/                         # 数据访问层
│   │
│   │   ├── models/                       # ORM模型
│   │   │   ├── user.py
│   │   │   ├── session.py
│   │   │   ├── message.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── memory.py
│   │   │   ├── audit_log.py
│   │   │   └── eval_result.py
│   │   │
│   │   ├── repositories/                 # Repository模式
│   │   │   ├── user_repo.py
│   │   │   ├── session_repo.py
│   │   │   ├── document_repo.py
│   │   │   └── memory_repo.py
│   │   ├── migrations/                   # Alembic迁移
│   │   ├── session.py                    # 数据库连接
│   │   └── base.py
│   │
│   ├── observability/                    # 可观测系统
│   │
│   │   ├── tracing/                      # 链路追踪
│   │   │   ├── tracer.py
│   │   │   └── decorators.py
│   │   │
│   │   ├── metrics/
│   │   │   └── metrics.py
│   │   │
│   │   ├── logging/                      # 日志系统
│   │   │   └── logger.py
│   │   │
│   │   └── audit/                        # 审计日志
│   │       └── audit_service.py
│   │
│   ├── evals/                            # Evals评测框架
│   │
│   │   ├── datasets/                     # 评测数据集
│   │   │   ├── legal/
│   │   │   └── finance/
│   │   ├── metrics/                      # 评测指标
│   │   │   ├── correctness.py
│   │   │   ├── groundedness.py
│   │   │   └── retrieval.py
│   │   ├── runner.py                     # 评测执行器
│   │   └── analyzer.py                   # Bad Case分析
│   │
│   ├── security/                         # 安全治理
│   │   ├── auth.py                       # 身份认证
│   │   ├── jwt.py                        # JWT鉴权
│   │   ├── permission.py                 # 权限控制
│   │   ├── prompt_guard.py               # Prompt注入防护
│   │   └── content_filter.py             # 内容过滤
│   │
│   ├── schemas/                          # Pydantic数据结构
│   ├── configs/                          # 配置管理
│   ├── utils/                            # 公共工具函数
│   └── main.py                           # FastAPI启动入口
│
├── data/                                # 本地数据目录
│   ├── raw_documents/                   # 原始文档
│   ├── parsed_documents/                # 解析结果
│   ├── eval_datasets/                   # 评测集
│   └── uploads/                         # 用户上传文件
│
├── scripts/                             # 运维与离线脚本
│   ├── build_index.py                   # 构建向量索引
│   ├── import_documents.py              # 导入知识库
│   ├── run_evals.py                     # 执行评测
│   └── benchmark.py                     # 性能测试
│
├── frontend/                            # 前端可视化
|
├── tests/                               # 测试代码
│   ├── runtime/                         # Runtime测试
│   ├── rag/                             # 检索测试
│   ├── tools/                           # 工具测试
│   ├── api/                             # API测试
│   └── integration/                     # 集成测试
│
├── deployment/                          # 部署配置
│   ├── docker/
│   ├── kubernetes/
│   └── nginx/
│
├── docs/                                # 项目技术文档
│   ├── architecture.md                  # 系统架构
│   ├── runtime_design.md                # Runtime设计
│   ├── rag_design.md                    # RAG设计
│   ├── database_design.md               # 数据库设计
│   ├── api_design.md                    # API设计
│   └── deployment.md                    # 部署文档
│
├── .env.example                         # 环境变量模板
├── docker-compose.yml                   # 本地开发环境
├── pyproject.toml                       # Python项目配置
├── README.md                            # 项目说明
└── Makefile                             # 常用开发命令
```

---

## 6. Agent Runtime

### 职责

Agent Runtime 是系统的核心控制器，负责把用户请求转换为一条可执行的任务链。其架构为：

```
Agent Runtime

├── State Manager
├── Planner
├── Router
├── Tool Executor
├── Memory Manager
├── Reflection Engine
└── Event Bus
```

### 建议执行阶段

1. **Planning**：识别意图，生成任务计划与子任务。
2. **Memory**：读取会话历史与长期记忆，补充上下文。
3. **Tool Use**：根据计划选择工具或 MCP 服务执行。
4. **Reflection**：检查结果是否满足目标，必要时重试或修正。

Agent执行流程：

```
User Query
      │
      ▼

Intent Recognition
      │
      ▼

Task Planning
      │
      ▼

Memory Retrieval
      │
      ▼

Knowledge Retrieval
      │
      ▼

Tool Calling
      │
      ▼

Reflection
      │
      ▼

Answer Generation
      │
      ▼

Final Response
```

### 混合决策流

建议采用：

- **ReAct**：用于需要“思考 → 行动 → 观察”的工具型任务；
- **Plan & Execute**：用于复杂任务拆解、长期任务、可循环任务；
- **Hybrid Orchestration**：根据任务难度、上下文长度和工具依赖进行动态切换。

### 关键能力

- 条件分支

- 中断恢复

- 失败重试

- 最大迭代次数控制

- 流式输出

- 任务超时处理

### State设计
```python
class AgentState:

    query: str

    messages: list

    intent: str

    plan: list

    retrieved_docs: list

    tool_results: list

    memories: list

    final_answer: str

    retries: int
```

State贯穿整个执行流程。

### Node设计

统一抽象：

```python
class BaseNode:

    async def execute(
        self,
        state: AgentState
    ):
        pass
```

### 系统节点：

```
IntentNode

PlannerNode

RetrieverNode

ToolNode

ReflectionNode

AnswerNode
```

### Router设计

负责决定当前节点执行完成后，下一步执行哪个节点。例如：

```
IntentNode
      │
      ▼

是否需要知识库？

 ├── 是 → RetrieverNode
 │
 └── 否 → ToolNode
```

### Reflection机制

Reflection用于质量控制。执行完成后评估：

```
信息是否充足

工具是否成功

答案是否完整

是否满足用户目标
```

若不满足：

```
重新规划
重新检索
重新执行工具
```

形成闭环：

```
Plan
 ↓
Execute
 ↓
Reflect
 ↓
Replan
```

---

## 7. 模型路由设计

### 职责

负责将不同模型 Provider 统一成一套调用接口，并根据任务场景动态路由。Router负责模型选择、负载均衡、降级切换、成本控制。

### 设计建议

- **统一模型接口**
  - `generate()`
  - `stream()`
  - `embed()`
  - `rerank()`
- **Provider Router**
  - 根据任务类型、成本、速度、上下文长度选择模型，统一抽象为LLMProvider，支持OpenAI、DeepSeek、Claude、GLM、Qwen等。
- **降级策略**
  - 主模型失败后切换备用模型
  - 长上下文任务优先选支持长上下文的 Provider
- **能力路由**
  - 搜索类任务 → 搜索工具
  - 数据类任务 → 数据库工具
  - 文档类任务 → 文档解析工具
  - 需要外部系统的任务 → MCP Server，如Filesystem MCP、Browser MCP、Browser MCP等。

## 8.  Tool Calling架构

建议把工具统一抽象为：

```text
Tool
├── name
├── description
├── input_schema
├── permission_scope
├── timeout
├── retry_policy
└── executor
```

并区分两类来源：

- **内部 Skill / API**
- **外部 MCP Server**

### Tool Registry

```
Tool Registry

├── Search Tool
├── SQL Tool
├── Knowledge Tool
├── File Tool
├── Browser Tool
└── MCP Tool
```

------

统一接口：

```python
class Tool:

    name

    description

    schema

    async execute()
```

---

## 9. 检索增强（RAG）

### 目标

在法律 / 金融等专业领域，单纯依赖向量召回通常不够稳定，需要结合关键词和语义召回。整体流程：

```
User Query
      │
      ▼

Query Rewrite
      │
      ▼

Hybrid Retrieval
      │
      ├──── BM25
      │
      └──── Vector Search
      │
      ▼

RRF Fusion
      │
      ▼

CrossEncoder Rerank
      │
      ▼

Context Builder
      │
      ▼

     LLM
```

### 知识库构建流程

1. 文档导入
2. 解析与清洗
3. 结构化分块
4. 生成 embedding
5. 建立 sparse + dense 索引
6. PostgreSQL + pgvector

支持PDF、DOCX、TXT、Markdown、HTML、Excel格式。

### 分块策略建议

根据领域文本特征做差异化分块：

- 法律文本：按法条、章节、条款、判决书段落切分；
- 金融文本：按标题层级、指标说明、产品说明、公告段落切分；
- 长文档：优先保持语义完整性，避免过度切碎；
- 表格类内容：优先结构化抽取后再入库。

### 召回策略建议

- **BM25**：适合精确术语、法条编号、专有名词。利用PostgreSQL全文索引`to_tsvector(content)`，查询`ts_rank()`；
- **向量召回**：适合语义相近、表达不一致的查询；Embedding字段`embedding vector(1024)`，查询```SELECT *
  FROM document_chunks
  ORDER BY embedding <=> query_embedding
  LIMIT 20;```
- **RRF**：融合BM25+向量两路结果生成统一候选集，降低单路召回偏差；
- **Rerank**：使用BGE-Reranker对前 N 条候选做重排序，提升最终上下文命中率。

---

## 10 记忆系统设计

### 记忆分层

- **短期记忆**：当前会话最近N轮消息；
- **摘要记忆**：对长会话做压缩摘要；
- **长期记忆**：用户偏好、常用领域偏好、历史任务结果；
- **任务记忆**：当前任务状态、子任务进度、工具返回结果、中间推理结果。

### 实现建议

- 记忆不要无限累积，避免上下文膨胀；
- 通过摘要压缩保留关键事实；
- 对敏感信息建立明确的访问控制与脱敏策略；
- 记忆写入要有触发条件，避免噪声污染。

---

## 11. 安全控制

### 目标

面向法律 / 金融等场景，平台必须具备基本安全边界。

### 建议机制

- 用户鉴权与角色权限控制：RBAC模型：Admin、Operator、User；
- 工具权限白名单；
- 敏感工具二次确认，数据库写入、文件修改、外部调用等敏感工具必须授权；
- Prompt 注入防护：检测Ignore Previous Instructions、System Prompt Leak、Role Override；
- 检索内容安全过滤；
- 审计日志保留；
- 关键操作留痕可追踪。

### 安全原则

1. 默认最小权限。
2. 默认不直接执行高风险工具。
3. 默认记录关键步骤。
4. 默认对外部输入做净化和约束。

---

## 12. API 与流式输出

### 接口建议

- `POST /chat`：发起对话
- `GET /chat/stream`：SSE 流式输出
- `POST /knowledge/index`：构建知识库索引
- `GET /knowledge/search`：检索测试
- `POST /evals/run`：执行评测
- `GET /audit/{trace_id}`：查询审计链路

### 流式返回内容建议

SSE 过程中可按阶段输出：

- `intent_detected`
- `plan_generated`
- `retrieval_started`
- `tool_called`
- `tool_result`
- `reflection`
- `final_answer`
- `error`

这样前端可以直接展示“正在思考”的过程，也便于调试与回放。

---

## 13. 数据库设计

### users

```SQL
id
username
role
created_at
```

------

### sessions

```SQL
id
user_id
title
created_at
```

------

### messages

```SQL
id
session_id
role
content
created_at
```

------

### documents

```SQL
id
domain
title
source
created_at
```

------

### document_chunks

```SQL
id
document_id
content
embedding
metadata
```

------

### memories

```SQL
id
user_id
memory_type
content
```

------

### audit_logs

```SQL
id
trace_id
action
payload
created_at
```

------

### eval_results

```SQL
id
dataset_name
metric
score
created_at
```

## 14. 可观测性设计

### 可观测性目标

把一次请求从头到尾串起来：

- 哪个模型被调用了
- 调用了哪些工具
- 检索了哪些文档
- 哪一步耗时最长
- 哪一步失败了
- 最终为什么输出这个答案

### 建议埋点

- 请求入口 trace
- Agent 节点 trace
- Tool 调用 trace
- 检索 trace
- 模型调用 trace
- 错误栈与重试记录
- 生成结果与引用文档记录

基于OpenTelemetry，记录：

```
Request Trace

LLM Trace

Tool Trace

Retrieval Trace

Reflection Trace

Error Trace
```

支持记录请求耗时、模型耗时、工具耗时、检索耗时、Token消耗、失败原因。

## 15. Evals评测体系

构建领域评测集：法律QA、金融QA等。

### 核心指标

- Answer Correctness
- Faithfulness / Groundedness
- Retrieval Recall
- Context Precision
- Tool Success Rate
- Average Latency
- Failure Recovery Rate

---

## 16. 关键实现路径

### 第一阶段：打通主链路

目标：先实现一个可用的最小闭环。

#### 交付物

- FastAPI 接口
- 单模型调用
- 基础对话状态
- SSE 流式输出
- 简单工具调用
- 简单知识库检索

#### 验收标准

- 能稳定完成一次完整对话；
- 能返回流式中间状态；
- 能检索到知识库文档；
- 能记录基础日志。

---

###  第二阶段：完善 Agent 编排

#### 交付物

- agent runtime
- Planning / Tool Use / Reflection 节点
- 条件分支与失败重试
- 模型路由与降级

#### 验收标准

- 复杂任务能自动拆解；
- 工具失败后能重试或换路；
- 长任务不会卡死在单个节点。

---

### 第三阶段：增强检索

#### 交付物

- 文档解析器
- 分块策略
- BM25 + 向量双路召回
- RRF
- Rerank

#### 验收标准

- 专业术语命中率提升；
- 长文档问答可用；
- 召回结果更稳定。

---

### 第四阶段：安全与观测

#### 交付物

- 权限控制
- 工具白名单
- 敏感操作拦截
- OpenTelemetry tracing
- Evals 闭环

#### 验收标准

- 请求能完整追踪；
- 高风险操作可拦截；
- bad case 可回溯、可修复。

---

## 17. 新增一个垂直领域的接入流程

当你要接入一个新领域，例如医疗、保险、企业制度，只需要按以下步骤做：

1. 准备领域 Prompt 模板；
2. 配置工具列表；
3. 准备知识库文档；
4. 选择分块策略；
5. 配置召回与重排参数；
6. 编写领域安全规则；
7. 创建对应评测集；
8. 进行回归测试。

理想情况下，新增领域不需要重写 Agent Runtime，只需要补充配置和少量领域适配代码。

---

## 18. 本项目推荐的配置文件

.env.example：

```env
APP_ENV=dev
APP_NAME=domain-ai-service

# LLM
DEFAULT_LLM_PROVIDER=
DEFAULT_LLM_MODEL=
FALLBACK_LLM_PROVIDER=
FALLBACK_LLM_MODEL=
LLM_API_KEY=

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/domain_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# Vector Store
CHROMA_PATH=./data/chroma

# Observability
OTEL_SERVICE_NAME=domain-ai-service
OTEL_EXPORTER_OTLP_ENDPOINT=

# Security
JWT_SECRET=
ADMIN_API_KEY=
```

---

## 19. 调试建议

- 先关闭复杂工具，只保留一个最简单工具；
- 先验证流式输出，再验证 Agent 编排；
- 先验证检索链路，再接入 rerank；
- 先做单领域，再扩展到多领域。

---

## 20. 测试建议

### 单元测试

- 模型路由测试
- Tool schema 测试
- 分块策略测试
- 记忆读写测试

### 集成测试

- 对话链路测试
- 检索链路测试
- 工具调用测试
- SSE 输出测试

### 回归测试

- 用 Evals 数据集固定测试集；
- 每次改 Prompt、召回、路由都要回归；
- 记录指标变化。

---

## 21. 里程碑建议

### M1：最小可用版本
- 单轮问答
- 简单工具调用
- 基础知识库检索

### M2：可用的行业助手
- Agent Runtime
- 多轮对话
- SSE 流式输出
- Redis 会话与缓存

### M3：稳定的生产化版本
- 模型路由
- 多路召回
- 重排
- Tracing
- Evals 闭环
- 安全策略

---

## 22. 参考实现优先级

建议按下面顺序实现：

1. API 与会话骨架
2. 单模型问答
3. 流式输出
4. 工具注册与调用
5. Agent Runtime 状态机
6. 记忆模块
7. 知识库解析与检索
8. RRF + Rerank
9. 安全与权限
10. Tracing 与 Evals

---

## 23. 参考技术文档

建议实现时对照以下官方文档：

- LangGraph：有状态、长生命周期 Agent 编排；
- MCP：标准化工具与外部系统接入；
- FastAPI：SSE / StreamingResponse；
- Redis：分布式限流与缓存；
- OpenTelemetry：traces / metrics / logs；
- PostgreSQL / pgvector：向量检索能力。

