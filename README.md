# DomainForge — 领域定制智能对话与知识服务平台

面向法律、金融、企业知识库等垂直领域场景构建的企业级 Agent 应用开发平台。平台以**自研 Agent Runtime** 为核心，集成**任务规划（Planning）、记忆管理（Memory）、工具调用（Tool Use）、结果反思（Reflection）**四阶段执行框架，实现多轮对话、知识检索、工具编排、会话记忆与安全审计能力，支持快速构建行业级 AI 助手。

---

## 核心特性

### Agent 能力

- **多轮对话** — 支持上下文感知的连续对话
- **意图识别** — 自动识别用户意图并引导任务流程
- **任务规划** — 复杂任务自动拆解为可执行子任务
- **工具调用** — 动态选择与调用内置工具或外部 MCP 服务
- **会话记忆** — 分层记忆管理（短期 / 摘要 / 长期）
- **结果反思** — 执行结果质量评估与自动纠错重试
- **流式输出** — SSE 实时推送执行中间状态

### RAG 能力

- **文档解析** — 支持 PDF、DOCX、Markdown、HTML 等多格式解析
- **向量检索** — 基于 pgvector 的语义向量召回
- **BM25 全文检索** — PostgreSQL 全文索引，适合精确术语匹配
- **Hybrid Search** — 双路召回融合
- **RRF 融合** — 降低单路召回偏差
- **CrossEncoder Rerank** — BGE-Reranker 重排序提升命中率
- **领域分块策略** — 法律文本按条款切分，金融文本按标题层级切分

### Tool 能力

- **Search Tool** — 搜索工具
- **SQL Tool** — 数据库查询工具
- **Knowledge Tool** — 知识库检索工具
- **Document Tool** — 文档处理工具
- **MCP Tool** — 外部 MCP 服务适配
- **Tool Registry** — 统一注册中心，支持权限声明与超时策略

### 企业能力

- **用户管理** — RBAC 角色权限模型（Admin / Operator / User）
- **会话管理** — 跨会话上下文持久化
- **权限控制** — 工具白名单与敏感操作二次确认
- **审计日志** — 关键操作全链路留痕
- **Tracing 监控** — 基于 OpenTelemetry 的请求链路追踪
- **Evals 评测** — 领域评测集与自动化指标评估

---

## 总体架构

系统采用五层分层设计：

| 层级 | 职责 |
| ---- | ---- |
| **交互层** | Web / API / SSE 流式输出 |
| **编排层** | Agent Runtime、任务规划、状态机、反思与重试 |
| **能力层** | 模型路由、Tool Calling、MCP 接入、内部 Skill |
| **数据层** | 知识库、会话、缓存、审计日志、评测集 |
| **可观测层** | Tracing、Monitoring、Error Tracking、Evals |

```
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
│  Planner | Memory | Tools | Reflect│
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
└────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│         OpenTelemetry              │
└────────────────────────────────────┘
```

### Agent Runtime 执行流程

```
User Query → Intent Recognition → Task Planning → Memory Retrieval
    → Knowledge Retrieval → Tool Calling → Reflection → Answer Generation
```

支持 **ReAct**（工具型任务）、**Plan & Execute**（复杂任务拆解）及 **Hybrid Orchestration**（动态切换）三种决策模式。

### 技术选型

| 模块 | 技术 |
| ---- | ---- |
| 后端框架 | FastAPI |
| Agent Runtime | 自研（State + Node + Router 架构） |
| 数据库 | PostgreSQL + pgvector |
| 缓存 | Redis |
| ORM | SQLAlchemy |
| 向量模型 | BGE-M3 |
| Rerank 模型 | BGE-Reranker |
| 工具协议 | MCP |
| 可观测 | OpenTelemetry |
| 鉴权 | JWT |
| 前端 | Next.js |
| 容器化 | Docker |

---

## 目录结构

```
domainforge/
│
├── app/                                  # 核心应用代码
│   ├── api/                              # API 接口层（FastAPI Router）
│   │   ├── chat.py                       # 对话接口
│   │   ├── knowledge.py                  # 知识库管理接口
│   │   ├── evals.py                      # 评测接口
│   │   ├── admin.py                      # 管理后台接口
│   │   └── health.py                     # 健康检查
│   │
│   ├── runtime/                          # Agent Runtime 核心引擎
│   │   ├── state/                        # Agent 状态管理
│   │   ├── planner/                      # 任务规划模块
│   │   ├── router/                       # 流程路由器
│   │   ├── nodes/                        # Runtime 执行节点
│   │   ├── reflection/                   # Reflection 机制
│   │   ├── events/                       # Runtime 事件总线
│   │   └── runtime.py                    # Agent Runtime 入口
│   │
│   ├── llm/                              # 大模型能力层
│   │   ├── providers/                    # 各模型 Provider 实现
│   │   ├── router/                       # 模型路由与降级
│   │   ├── embedding/                    # Embedding 服务
│   │   ├── rerank/                       # Rerank 服务
│   │   └── base.py                       # LLM 统一抽象接口
│   │
│   ├── tools/                            # Tool Calling 体系
│   │   ├── registry/                     # Tool 注册中心
│   │   ├── builtin/                      # 内置工具
│   │   ├── mcp/                          # MCP 协议适配层
│   │   └── base.py                       # Tool 统一接口
│   │
│   ├── rag/                              # 检索增强系统
│   │   ├── parser/                       # 文档解析
│   │   ├── chunk/                        # 文本切块策略
│   │   ├── retrieval/                    # 检索算法
│   │   ├── indexing/                     # 建库流程
│   │   ├── context/                      # 上下文构造
│   │   └── service.py                    # RAG 统一服务入口
│   │
│   ├── memory/                           # 记忆系统
│   │   ├── short_term/                   # 短期记忆
│   │   ├── summary/                      # 摘要记忆
│   │   ├── long_term/                    # 长期记忆
│   │   ├── manager.py                    # 记忆调度器
│   │   └── memory_service.py             # 记忆服务
│   │
│   ├── database/                         # 数据访问层
│   │   ├── models/                       # ORM 模型
│   │   ├── repositories/                 # Repository 模式
│   │   ├── migrations/                   # Alembic 迁移
│   │   ├── session.py                    # 数据库连接
│   │   └── base.py                       # 数据库基类
│   │
│   ├── observability/                    # 可观测系统
│   │   ├── tracing/                      # 链路追踪
│   │   ├── metrics/                      # 指标采集
│   │   ├── logging/                      # 日志系统
│   │   └── audit/                        # 审计日志
│   │
│   ├── evals/                            # Evals 评测框架
│   │   ├── datasets/                     # 评测数据集
│   │   ├── metrics/                      # 评测指标
│   │   ├── runner.py                     # 评测执行器
│   │   └── analyzer.py                   # Bad Case 分析
│   │
│   ├── security/                         # 安全治理
│   │   ├── auth.py                       # 身份认证
│   │   ├── jwt.py                        # JWT 鉴权
│   │   ├── permission.py                 # 权限控制
│   │   ├── prompt_guard.py               # Prompt 注入防护
│   │   └── content_filter.py             # 内容过滤
│   │
│   ├── schemas/                          # Pydantic 数据结构
│   ├── configs/                          # 配置管理
│   ├── utils/                            # 公共工具函数
│   └── main.py                           # FastAPI 启动入口
│
├── data/                                 # 本地数据目录
│   ├── raw_documents/                    # 原始文档
│   ├── parsed_documents/                 # 解析结果
│   ├── eval_datasets/                    # 评测集
│   └── uploads/                          # 用户上传文件
│
├── scripts/                              # 运维与离线脚本
│   ├── build_index.py                    # 构建向量索引
│   ├── import_documents.py               # 导入知识库
│   ├── run_evals.py                      # 执行评测
│   └── benchmark.py                      # 性能测试
│
├── frontend/                             # 前端可视化
│
├── tests/                                # 测试代码
│   ├── runtime/                          # Runtime 测试
│   ├── rag/                              # 检索测试
│   ├── tools/                            # 工具测试
│   ├── api/                              # API 测试
│   └── integration/                      # 集成测试
│
├── deployment/                           # 部署配置
│   ├── docker/
│   ├── kubernetes/
│   └── nginx/
│
├── docs/                                 # 项目技术文档
│   ├── architecture.md                   # 系统架构
│   ├── runtime_design.md                 # Runtime 设计
│   ├── rag_design.md                     # RAG 设计
│   ├── database_design.md                # 数据库设计
│   ├── api_design.md                     # API 设计
│   └── deployment.md                     # 部署文档
│
├── .env.example                          # 环境变量模板
├── docker-compose.yml                    # 本地开发环境
├── pyproject.toml                        # Python 项目配置
├── README.md                             # 项目说明
└── Makefile                              # 常用开发命令
```

---

## 实现路径

平台分四个阶段渐进构建：

### 第一阶段：打通主链路
FastAPI 接口、单模型调用、基础对话状态、SSE 流式输出、简单工具调用、基础知识库检索。

### 第二阶段：完善 Agent 编排
Agent Runtime 状态机、Planning 节点、Reflection 节点、条件分支与失败重试、模型路由与降级。

### 第三阶段：增强检索
文档解析器、领域分块策略、BM25 + 向量双路召回、RRF 融合、CrossEncoder Rerank。

### 第四阶段：安全与观测
RBAC 权限控制、工具白名单、敏感操作拦截、OpenTelemetry Tracing、Evals 评测闭环。

---

## 快速开始

> 文档待完善

---

## 使用

> 文档待完善

---

## 贡献

### 分支策略

- `main` — 稳定版本，仅接受 PR 合并
- `feat/*` — 特性开发分支
- `fix/*` — 修复分支

### 开发流程

1. Fork 本仓库并创建你的特性分支
2. 编写代码并补充对应测试
3. 确保所有测试通过
4. 提交 Pull Request

### 测试指南

- **单元测试**：模型路由、Tool Schema、分块策略、记忆读写
- **集成测试**：对话链路、检索链路、工具调用、SSE 输出
- **回归测试**：使用 Evals 数据集固定测试集，每次改 Prompt / 召回 / 路由后回归

### 调试建议

- 先关闭复杂工具，只保留一个最简单工具
- 先验证流式输出，再验证 Agent 编排
- 先验证检索链路，再接入 Rerank
- 先做单领域，再扩展到多领域

---

## 新增垂直领域

接入新领域（如医疗、保险、企业制度）只需：

1. 准备领域 Prompt 模板
2. 配置工具列表
3. 准备知识库文档
4. 选择分块策略
5. 配置召回与重排参数
6. 编写领域安全规则
7. 创建对应评测集
8. 进行回归测试

理想情况下，新增领域不需要重写 Agent Runtime，只需要补充配置和少量领域适配代码。
