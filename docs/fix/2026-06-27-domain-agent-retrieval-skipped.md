# 修复：领域 Agent 绑定后"无反应"——意图为 chat 时跳过检索导致 LLM 幻觉查询标签

> 日期：2026-06-27
> 类型：行为修复（领域 agent 在 chat 意图下拿不到领域知识，转而幻觉出 `<knowledge_base_query>` 标签而非作答）
> 影响范围：`/api/v1/chat` 与 `/chat/stream` 主回答链路；仅在 `session.agent_id` 绑定领域 agent 时触发

## 1. 问题现象

用户在前端选择"法律咨询"agent 后提问：

> 宪法如何规定国徽？

前端"没有任何反应"。后端日志显示请求**已完整处理并落库**，assistant 消息内容为：

```
好的，我马上为您检索法律知识库中关于宪法如何规定国徽的相关内容。

<knowledge_base_query>
<knowledge_base>legal</knowledge_base>
<query>宪法 国徽 规定 第四章 国旗 国歌 国徽 首都</query>
</knowledge_base_query>
```

即：agent 声称要去检索，却输出了一个**自造的 `<knowledge_base_query>` 标签**，没有给出任何实际回答。SSE `final_answer` 事件确实下发，前端 react-markdown 也确实把标签作为转义文本渲染（不会崩溃），但用户看到的是"说要检索、却只给了一个查询标签"——从用户视角即"没有反应"。

## 2. 根因分析

三层叠加，核心是**领域 agent 的检索被意图分类器意外短路**。

### 2.1 意图分类器把领域问题判为 `chat`

`app/runtime/nodes/intent_node.py` 用 LLM 把 query 分为 `chat / knowledge / tool`。实测 deepseek-v4-pro 对"宪法如何规定国徽"几乎稳定判为 `chat`（即便加"请检索法律知识库中…"前缀也是 `chat`）。这是模型行为，难以靠 prompt 强约束。

### 2.2 RetrievalNode 仅在 `intent == "knowledge"` 时执行

修复前 `app/runtime/nodes/retrieval_node.py`：

```python
async def execute(self, state: AgentState) -> AgentState:
    if state.intent != "knowledge":
        return state  # ← chat 意图直接跳过，不论是否绑定了领域 agent
    ...
```

`ConditionalStrategy._will_run`（`app/runtime/router/strategy.py`）同样只看 intent 与 plan：

```python
if name == "retrieval":
    return state.intent == "knowledge" or _plan_needs(state, "retrieve")
```

结果：**领域 agent 绑定（`state.agent_domain = "legal"`）后，检索仍被跳过**。legal 知识库里有 2 篇文档 / 4654 字，但 agent 拿不到任何片段。

### 2.3 AnswerNode 在无检索上下文时被 agent system_prompt 诱导幻觉

`app/runtime/nodes/answer_node.py` 在 `state.agent_system_prompt` 非空时改用 agent 自带 prompt。法律 agent 的 system_prompt 是：

> 你是一名专业的法律咨询助手。请严格依据检索到的法律知识（法条、案例、条款）回答用户问题。
> 1. 优先引用检索到的知识库内容；若知识库无相关内容，明确告知并提示用户补充信息，不得编造法条或案例。

同时 `_build_capability_context()` 会把可用工具清单注入 context，其中包含：

> - knowledge_search: 搜索知识库文档，返回与查询相关的文档片段

LLM 看到"必须依据检索到的法律知识"但 `retrieved_docs` 为空，又看到 `knowledge_search` 工具描述，便**自造了一种 `<knowledge_base_query>` 标签语法**试图"发起检索"——这是模型对工具调用格式的幻觉，系统并不识别该标签。最终 `state.final_answer` 被设为这段无用文本并落库。

### 2.4 为什么用户感知是"没有反应"

- `final_answer` 事件已下发，前端 StreamingBubble 会渲染该文本。
- 但文本内容是"好的，我马上为您检索… + 一个查询标签"，**没有任何实质回答**。
- 用户期待的是宪法条文，看到的是 agent 自言自语要检索——等同于 agent 没有完成任务。

## 3. 解决方案

**核心思路**：领域 agent 的存在本身（`agent.domain` 非空）就表明需要领域知识，不应再依赖意图分类器决定是否检索。让 `agent_domain` 非空时**强制触发检索**，并让检索失败可降级，避免拖垮主链路。

### 3.1 `ConditionalStrategy._will_run` 放行领域 agent 的检索

`app/runtime/router/strategy.py`

```python
def _will_run(self, state: AgentState, name: str) -> bool:
    if name == "retrieval":
        return (
            state.intent == "knowledge"
            or _plan_needs(state, "retrieve")
            or bool(state.agent_domain)  # ← 新增：领域 agent 强制检索
        )
    ...
```

### 3.2 `RetrievalNode.execute` 同步放开守卫

`app/runtime/nodes/retrieval_node.py`

```python
async def execute(self, state: AgentState) -> AgentState:
    # agent_domain 非空时强制检索（领域 agent 必须拿到领域知识上下文）
    if state.intent != "knowledge" and not state.agent_domain:
        return state
    ...
```

两处必须同时改：`_will_run` 决定 Router 是否调用该节点，`execute` 内的守卫决定节点自身是否短路。只改一处会导致节点被跳过或被调用后立即返回。

### 3.3 检索失败降级，不阻断主链路

领域 agent 强制检索后，检索后端不可用（如测试环境 SQLite 不支持 pgvector 的 `<=>` 算子、或生产 pgvector 扩展缺失）会直接抛异常。`RetrievalNode` 现在 catch 异常、记日志、返回空 `retrieved_docs`，让 AnswerNode 仍可基于能力上下文作答：

```python
try:
    chunks = await self.rag_service.search(state.query, domain=state.agent_domain)
except Exception as e:
    logger.warning("retrieval_failed", error=str(e), domain=state.agent_domain)
    state.retrieved_docs = []
    return state
```

与 `AnswerNode._build_capability_context` 的"子查询失败降级"同构，保证主链路鲁棒性。

### 3.4 不在本次做的事

- **不改意图分类器**：deepseek-v4-pro 把领域问题判为 `chat` 是模型行为，强行改 prompt 不可靠；且领域 agent 强制检索后，意图是否为 `knowledge` 已不再影响检索触发。
- **不应用 agent.temperature**：`_llm_for_agent` 未把 `agent.temperature` 注入 provider，是另一独立问题（所有 agent 都用默认温度），不在本 bug 范围。留作后续。
- **不缓存检索结果**：与 [[agent_capability_visibility]] 的"不缓存能力上下文"同理，每次实时检索保证新鲜度。

## 4. 改动清单

| 文件 | 改动 |
|---|---|
| `app/runtime/router/strategy.py` | `_will_run` 新增 `or bool(state.agent_domain)` 放行 retrieval |
| `app/runtime/nodes/retrieval_node.py` | 守卫改为 `intent != "knowledge" and not agent_domain`；检索失败 try/except 降级；引入 `get_logger` |
| `tests/runtime/test_runtime_hardening.py` | 新增 `test_retrieval_forced_when_agent_domain_set`：agent_domain 非空 + intent=chat 时断言 retrieval 执行 |

## 5. 验证

### 5.1 单测

- 新增 `test_retrieval_forced_when_agent_domain_set`：构造 intent=chat + agent_domain="legal"，断言 retrieval 节点 `started_at` 非空且 `retrieved_docs` 被写入。修复前该测试失败（retrieval 被跳过），修复后通过。
- `pytest tests/` 全量：**197 passed**，无回归。

### 5.2 端到端（运行中的后端 + legal agent）

绑定 legal agent（`domain="legal"`）后连续 3 个新会话提问"宪法如何规定国徽"，SSE 事件序列稳定为：

```
intent_detected × 2  (status=recognizing + intent=chat)
retrieval_started × 1  ← 修复前缺失
final_answer × 1
knowledge_base_query 标签出现次数: 0  ← 修复前偶发
```

修复后典型回答（基于真实检索结果）：

> 根据知识库检索，未找到关于国徽的具体宪法条文。当前知识库中仅包含宪法部分条款（如第四十条至第五十一条），但这些条款并未涉及国徽的规定……建议您查阅正式法律文本或通过官方渠道确认。

agent 现在据实回答"KB 里没有国徽相关条文"，而非幻觉查询标签。

### 5.3 兼容性

- 非 agent 场景（`agent_domain` 为空）：行为完全不变，仍由 intent 决定是否检索。
- 检索后端异常：主链路不再 500，agent 降级作答。

## 6. 后续方向（P1/P2）

- **P1**：`_llm_for_agent` 应把 `agent.temperature` 注入 provider，避免领域 agent 用默认温度（0.7）放大幻觉。当前所有 agent 的 temperature 字段实际未生效。
- **P1**：意图分类器对领域 agent 的 query 可考虑强制判为 `knowledge`（在 `IntentNode` 里 `if state.agent_domain: state.intent = "knowledge"`），与本修复双保险。
- **P2**：`<knowledge_base_query>` 这类自造标签可考虑在 `AnswerNode` 输出侧做一次 sanitize/告警，作为模型幻觉的兜底信号。
