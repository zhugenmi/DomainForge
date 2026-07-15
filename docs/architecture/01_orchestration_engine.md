# 01 编排引擎设计：可插拔 Agent Runtime

> 版本：0.1.0 | 日期：2026-06-17 | 对应代码：`app/runtime/`

---

## 1. 设计目标

构建一个**可插拔、可观测、可回放**的 Agent Runtime，把"理解 → 规划 → 记忆 → 检索 → 工具 → 作答 → 反思"这一链路抽象为状态机，使节点可替换、路由可重写、流程可流式输出。

核心约束：

- **业务等价优先**：任何重构不得改变对外契约（`/chat`、`/chat/stream` 的请求/响应结构、SSE 事件类型）。
- **依赖注入**：节点不自己 `import` 全局单例，全部由 `AgentRuntime` 在构造时注入。
- **流式优先**：每个节点执行过程中产生的中间状态都能通过 `EventBus` 实时推给客户端。

---

## 2. 三层抽象：State + Node + Router

### 2.1 AgentState —— 贯穿流程的可变数据载体

`app/runtime/state/agent_state.py`

```python
@dataclass
class AgentState:
    query: str
    messages: list[dict[str, str]] = []      # 对话历史
    intent: str = ""                          # chat / knowledge / tool
    plan: list[dict] = []                     # Planner 产出的步骤
    retrieved_docs: list[dict] = []           # RAG 召回
    tool_results: list[dict] = []             # 工具执行结果
    memories: list[dict[str, str]] = []       # 记忆上下文
    final_answer: str = ""
    retries: int = 0
    max_retries: int = 3
```

`AgentState` 是 dataclass，**不是** ORM 模型，不落库。它只在一次 `runtime.run()` 调用内存活。会话级别的持久化由 `MessageRepo` + `SessionRepo` 在 API 层完成。

`_reflection_reroute`（运行时动态属性）是 Reflection 节点回写给 Router 的重路由信号，取值 `retrieval` / `tool`，由 `ConditionalStrategy` 消费后清空。

### 2.2 BaseNode —— 统一节点接口

`app/runtime/nodes/base.py`

```python
class BaseNode(ABC):
    @abstractmethod
    async def execute(self, state: AgentState) -> AgentState: ...
```

每个节点只关心 `state` 的读写，不关心上下游是谁。节点之间通过 `state` 隐式通信，避免显式依赖。新增节点只需：

1. 继承 `BaseNode`，实现 `execute`。
2. 在 `AgentRuntime._build_router` 中注册。
3. （可选）在 `ConditionalStrategy` 的 `order` 中插入位置。

### 2.3 Router —— 决定节点执行顺序与跳过逻辑

`app/runtime/router/router.py` + `strategy.py`

Router 持有两种执行策略，构造时切换：

| 策略 | 行为 | 用途 |
|------|------|------|
| `LinearStrategy` | 顺序执行所有节点 | 兼容 Phase 1 测试、调试 |
| `ConditionalStrategy`（默认） | 按 `intent` + `plan` 跳过无用节点；支持 reflection 重路由 | 生产路径 |

`ConditionalStrategy` 的核心循环（节选）：

```python
while i < len(self.order) and iterations < self.max_iterations:
    name = self.order[i]
    if name == "retrieval" and state.intent != "knowledge" and not _plan_needs(state, "retrieve"):
        i += 1; continue
    if name == "tool" and state.intent != "tool" and not _plan_needs(state, "tool"):
        i += 1; continue
    state = await self.nodes[name].execute(state)
    reroute = getattr(state, "_reflection_reroute", None)
    if reroute:
        i = self.order.index(reroute)   # 回跳到 retrieval / tool
    else:
        i += 1
```

`_plan_needs(state, action)` 检查 Planner 是否规划了某类动作——这是 Planner 与 Router 之间的契约：**Planner 决定"要不要"，Router 决定"何时执行"**。

> 注：旧文件 `app/runtime/router/condition.py`（含未被引用的 `plan_has_action`）已在本次优化中删除，逻辑统一收敛到 `strategy.py::_plan_needs`。

---

## 3. 四阶段执行框架

design.md §3.1 定义的四阶段——Planning、Memory、Tool Use、Reflection——在 Runtime 中落地为以下节点链：

```
IntentNode → PlannerNode → MemoryNode → RetrievalNode → ToolNode → AnswerNode → ReflectionNode
   (意图)      (规划)        (记忆)        (检索)         (工具)     (作答)        (反思)
```

### 3.1 Planning：ReAct + Plan&Execute 混合

`app/runtime/planner/`

**何时规划**：`task_decomposer.needs_planning(query)` 用关键词启发式判断（"对比 / 比较 / 首先 / 然后 / 步骤 / between / compare" 且 `len(query) >= 12`）。简单闲聊直接跳过 Planner，避免无谓的 LLM 调用——这是 ReAct 的"按需思考"思想。

**如何规划**：`PlannerNode` 用 `PLANNING_PROMPT` 让 LLM 输出 JSON 步骤数组，`parse_plan` 做容错解析（去 markdown fence、正则兜底提取 `\[.*\]`）。每步结构 `{"step": "...", "action": "retrieve|tool|answer"}`，`action` 字段就是 Router 的跳过判定依据。

**混合决策**：
- **Plan&Execute 部分**：Planner 一次性产出多步计划写入 `state.plan`，Router 据此决定 retrieval/tool 是否执行。
- **ReAct 部分**：ToolNode 内部用 OpenAI function-calling 让 LLM 在执行期动态决定调用哪个工具、传什么参数——这是"边执行边思考"。

二者不冲突：Planner 决定"这一轮要不要走工具分支"，ToolNode 决定"具体调哪个工具"。

### 3.2 Memory：三层记忆统一入口

`app/memory/`

`MemoryService` 是 Runtime 唯一的记忆依赖（注入到 `AgentRuntime.memory_manager`）：

| 层 | 实现 | 作用 |
|----|------|------|
| 短期 | `BufferMemory` | 当前会话最近 N 轮（`SHORT_TERM_MEMORY_SIZE`，默认 20），落 `messages` 表 |
| 摘要 | `SummaryMemory` | 超阈值时 LLM 压缩历史为摘要，落 `memories` 表 |
| 长期 | `VectorMemory` | 跨会话语义召回，向量化存 `memories` 表，按 query 检索 top_k=3 |

`MemoryNode.execute` 调 `memory_manager.get_context()` 拼装上下文写入 `state.memories`，供 AnswerNode 使用。

> 类型修正：`AgentRuntime.__init__` 与 `MemoryNode.__init__` 的形参类型已从 `MemoryManager`（仅短期记忆的旧类）改为 `MemoryService`（三层统一入口），与 `chat.py::_build_runtime` 实际传入的对象一致。`MemoryManager` 仍保留供测试与轻量场景使用。

### 3.3 Tool Use：function-calling + Registry

`app/tools/` + `app/runtime/nodes/tool_node.py`

- **Registry**（`app/tools/registry/registry.py`）：进程级单例 `registry`，`register / get / list_tools / get_openai_tools`。`get_openai_tools()` 把 `ToolSchema` 转成 OpenAI tools 协议。
- **ToolNode**：当 `intent == "tool"` 或 plan 含 `tool` 动作时执行。调 `self.llm.client.chat.completions.create(tools=..., tool_choice="auto")`，逐个执行 `tool_calls`，结果写 `state.tool_results` 并发 `TOOL_CALLED` / `TOOL_RESULT` 事件。

> **已解除**(Phase 4):`ToolNode` 现走 `LLMProvider.chat_with_tools` 抽象,不再直连 `llm.client`。`chat_with_tools` 默认抛 `NotImplementedError`(非抽象),`FallbackPolicy` 捕获后跳过该 provider。详见 [adr/0006-llmprovider-default-not-implemented.md](../adr/0006-llmprovider-default-not-implemented.md)。

### 3.4 Reflection：评估 + 重路由 + 重试预算

`app/runtime/reflection/`

- `evaluator.evaluate_answer` 用 `REFLECTION_PROMPT` 让 LLM 输出 `{sufficient, reason, next_action}`，next_action ∈ `none / retrieve / tool / answer`。解析失败默认 `sufficient=True`，**避免反思失败导致死循环**。
- `ReflectionNode`：若 `sufficient` 或超出 `RetryPolicy.max_retries`（默认 2），直接返回；否则 `retries += 1` 并写 `_reflection_reroute` 让 Router 回跳。
- `RetryPolicy`：纯计数策略，`should_retry(retries) = retries < max_retries`。

> 旧文件 `app/runtime/reflection/critic.py`（含未被引用的 `analyze_failure`）已删除——失败分类逻辑从未接入执行链路，删除避免误导。

---

## 4. 流式输出：EventBus

`app/runtime/events/event_bus.py`

基于 `asyncio.Queue` 的单生产者-多事件消费者模型：

```python
async def run_stream(self, state):
    event_bus = EventBus()
    router = self._build_router(event_bus)

    async def _execute():
        try:
            await router.run(state)
        except Exception as e:
            await event_bus.publish_error(str(e))
        finally:
            event_bus.done()        # 推 None 终止

    task = asyncio.create_task(_execute())
    async for chunk in event_bus.stream():
        yield chunk                  # 已是 "data: {...}\n\n" 格式
    await task
```

SSE 事件类型枚举见 `event_type.py`：`INTENT_DETECTED / PLAN_GENERATED / RETRIEVAL_STARTED / TOOL_CALLED / TOOL_RESULT / REFLECTION / FINAL_ANSWER / ERROR`。

**关键不变量**：`event_bus.done()` 必须在 `finally` 中调用，否则消费者协程会永久阻塞。`run_stream` 在 `yield` 完所有事件后 `await task` 确保 `_execute` 真正结束，避免任务泄漏。

---

## 5. 可插拔点一览

| 扩展点 | 当前实现 | 替换方式 |
|--------|---------|---------|
| 节点 | 7 个 BaseNode 子类 | 新增子类 + 注册到 `_build_router` |
| 路由策略 | Linear / Conditional | 实现 `async run(state) -> state`，构造 Router 时传入 |
| 记忆后端 | Buffer / Summary / Vector | 实现 `get_context() / add_message()`，注入 `MemoryService` |
| LLM | OpenAI 兼容 | 实现 `LLMProvider` ABC，注册到 `ModelRouter._PROVIDERS` |
| 工具 | 6 个内置 + MCP | 实现 `Tool` ABC，`registry.register(tool)` |
| 检索 | vector / bm25 / hybrid | `RAGService(mode=...)` 或注入自定义 retriever |

---

## 6. 当前限制与后续方向

1. **ToolNode 绕过 LLMProvider 抽象**:**已解除**(Phase 4)。`LLMProvider.chat_with_tools` 抽象 + `ToolNode` 改走抽象,见 [adr/0006-llmprovider-default-not-implemented.md](../adr/0006-llmprovider-default-not-implemented.md)。
2. **Planner 启发式偏粗**:**部分解除**(Phase 4)。`IntentNode` 新增 `infer_complexity(query)` 关键词启发式(low/medium/high),`should_plan(state)` 以 complexity 为主、`needs_planning` 为辅。仍未用 LLM 判断 complexity。
3. **Reflection 单轮**:当前只评估最终答案,不评估中间步骤。多步任务的错误定位能力有限。
4. **无并行节点**:**已解除**(Phase 4)。`ConditionalStrategy` 在 retrieval 与 tool 都将执行时 `asyncio.gather` 并行,字段不重叠(`retrieved_docs` vs `tool_results`)无写竞争。
