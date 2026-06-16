# DomainForge：领域定制可插拔智能 Agent 编排平台

一个基于 LangChain + LangGraph 构建的企业级智能 Agent 编排平台，支持多模型统一治理、复杂任务规划、多 Agent 协作、RAG 检索增强与 MCP 工具生态接入，能够快速适配不同垂直领域的智能应用场景。

项目目标是构建一个具备“复杂任务推理 + 工程化治理 + 可扩展能力编排”的通用 Agent Runtime 平台，使其能够真正应用于企业级 AI Agent 场景，包括知识助手、代码助手、数据分析助手、业务自动化、Research Agent 等复杂任务系统。

## 项目背景

随着大模型能力不断提升，AI 应用逐渐从单轮问答演进到具备任务规划、工具调用、长期记忆与自主执行能力的 Agent 系统。但在真实企业场景中，传统单链路 Prompt 应用存在明显问题：

- 无法处理复杂任务拆解
- Tool 调用链路难以管理
- 多模型切换成本高
- RAG 检索质量不稳定
- Agent 缺乏可观测性
- 难以适配不同行业场景

因此，本项目尝试从“Agent Operating System”的角度出发，构建一套可插拔、可扩展、可观测的智能 Agent 编排平台。

整个系统围绕“任务规划、能力调度、检索增强、状态管理、可观测性”五个核心方向展开设计。

## 系统整体架构

平台整体采用分层式架构设计，由 Agent 编排层、模型与能力层、RAG 检索层、服务层与 Observability 层组成。

                        ┌────────────────────┐
                        │      Frontend      │
                        └─────────┬──────────┘
                                  │
                          REST API / SSE
                                  │
                    ┌─────────────┴─────────────┐
                    │      Agent Runtime        │
                    └─────────────┬─────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        Planner Engine      Tool Calling        RAG Engine
              │                   │                   │
      LangGraph State      MCP / Skills       Hybrid Retrieval
              │                   │                   │
              └───────────────────┴───────────────────┘
                                  │
                        Multi-LLM Router
                                  │
         ┌───────────────┬───────────────┬───────────────┐
         │               │               │
       GPT            Claude         Qwen/DeepSeek       *

平台核心采用 LangGraph 状态机驱动 Agent Workflow，通过 Planner + ReAct Hybrid 模式实现复杂任务推理与动态工具调用。

## 核心设计理念
### Agent Runtime 可插拔

项目将 Agent Runtime 抽象为统一运行时接口，不同领域可以通过替换 Prompt、Workflow、ToolChain 与 RAG 配置快速定制专属 Agent。

例如：

- 法律领域：法规检索 + 合同分析
- 金融领域：数据分析 + 报告生成
- 运维领域：日志分析 + 故障定位
- Coding Agent：代码生成 + 仓库分析

这种 Runtime 解耦设计可以显著降低垂直行业 AI Agent 的适配成本。

### ReAct + Plan&Execute 混合架构

系统并未采用单一 Agent Workflow，而是根据任务复杂度动态切换执行策略。

对于简单任务，系统采用 ReAct 模式，通过 Thought → Action → Observation 的循环快速完成 Tool Calling。

对于复杂任务，则进入 Planner 模式，将目标拆解为多个子任务，再交由不同 Agent 或 Tool 执行。

例如：
```text
用户需求：
“帮我分析这个 GitHub 项目的技术架构并生成总结报告”
系统执行：
1. 项目结构分析
2. README 解析
3. 技术栈识别
4. 代码摘要生成
5. 总结报告生成
```

相比传统单链路 Prompt，这种架构能够更稳定地处理复杂任务。

### 多模型统一治理

为了避免系统与单一模型强绑定，平台设计了统一 LLM Provider 层，对不同模型进行标准化封装。

当前支持：

- OpenAI GPT 系列
- Claude
- MiniMax
- DeepSeek
- Qwen

系统会根据：

- 推理复杂度
- Token 成本
- 响应延迟
- Tool Calling 能力

动态选择最合适的模型。

例如：

- 复杂推理任务优先使用 Claude / GPT-4
- 高并发低成本任务使用 Qwen
- 多模态场景使用 Gemini

同时支持模型降级与 Failover，避免单点故障。

### Tool Calling 与 MCP 能力体系

平台构建了统一 Tool Registry，将所有工具以标准 JSON Schema 描述。

系统支持：

- Web Search
- SQL Query
- 文件系统
- 浏览器操作
- GitHub 分析
- 文档解析
- API 调用

同时兼容 MCP（Model Context Protocol）生态，可动态接入外部 MCP Server。

例如：

- filesystem
- github
- postgres
- notion
- browser

Agent 会根据任务自动规划 Tool 调用链路。

相比传统“写死 Tool”的方式，这种能力编排体系具有更好的扩展性。

### Hybrid RAG 检索增强

为了提升知识问答质量，平台采用 Hybrid Retrieval 方案，而非单纯向量检索。

系统同时构建：

- BM25 倒排索引
- Dense Embedding 向量索引

再通过 RRF（Reciprocal Rank Fusion）融合多路召回结果，并使用 Rerank 模型进行二阶段排序。

整体流程如下：
```text
Query
  ↓
BM25 Recall
  ↓
Vector Recall
  ↓
RRF Fusion
  ↓
Rerank
  ↓
Context Builder
  ↓
LLM
```
这种方案相比单向量检索能够显著提升：

- 专有名词召回
- 长文本检索
- 精确知识问答

知识库支持多源数据文档：

- PDF
- DOCX
- Markdown
- HTML
- Excel

并针对领域文档定制 Chunk 切分与 Metadata 策略。

### 流式推理与用户体验

平台支持基于 SSE 的流式输出。

用户可以实时看到 Agent 的：

- Thinking
- Tool Calling
- Retrieval
- Reflection

例如：
```text
[Thinking...]
[Searching papers...]
[Calling SQL Tool...]
[Generating summary...]
```
这种“可见推理链路”的交互方式相比传统 ChatBot 更符合 Agent 产品形态。

### 可观测性与评测体系

由于 Agent 系统具备非确定性，因此项目重点建设了 Observability 能力。

系统基于 OpenTelemetry 构建全链路 Tracing，能够追踪：

- LLM 调用
- Tool 执行
- RAG 检索
- Token 消耗
- 错误链路

同时构建 Evals 评测体系，对：

- Prompt
- Retrieval
- Agent Workflow

进行自动化评估。

平台还设计了 Bad Case 闭环机制：
```text
线上失败案例
    ↓
自动收集
    ↓
人工标注
    ↓
Prompt/RAG优化
    ↓
重新评测
```
从而实现持续迭代优化。

技术栈

本项目主要技术栈如下：
```text
LLM Framework:
- LangChain
- LangGraph

Backend:
- FastAPI
- Redis
- PostgreSQL

RAG:
- Chroma
- FAISS
- BM25
- BGE Embedding

Observability:
- OpenTelemetry
- LangSmith

Infrastructure:
- Docker
- Nginx
- Celery

Protocols:
- MCP (Model Context Protocol)
```
## 项目亮点

该项目的核心价值并不只是“调用大模型”，而是尝试解决企业级 AI Agent 落地过程中最关键的问题：

- 如何稳定执行复杂任务
- 如何治理多模型
- 如何构建可扩展 Tool 生态
- 如何提升 RAG 检索质量
- 如何实现可观测与可评测
- 如何降低行业适配成本

相比传统 AI Demo，本项目更加偏向真实工程化 Agent 系统设计。

## 后续规划

后续计划：

- [ ] 多 Agent 协作机制
- [ ] 长期记忆（Long-Term Memory）
* [ ] Agent Marketplace
* [ ] Workflow 可视化编排
- [ ] 多模态 Agent
- [ ] 自动 Prompt 优化
- [ ] Self Reflection / Self Correction

进一步增强平台的自主推理与复杂任务执行能力。