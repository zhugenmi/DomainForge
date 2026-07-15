# 02 模型与能力层：多 Provider 路由 + Tool Registry + MCP

> 版本：0.1.0 | 日期：2026-06-17 | 对应代码：`app/llm/`、`app/tools/`

---

## 1. 设计目标

把"调哪个模型""用什么工具"从业务代码中剥离，统一收敛到能力层。业务侧（Runtime、API）只看到 `LLMProvider` 与 `ToolRegistry` 两个抽象，不感知具体厂商 SDK 与工具协议。

---

## 2. LLM Provider 统一封装

### 2.1 抽象接口

`app/llm/base.py`

```python
class LLMProvider(ABC):
    async def generate(self, messages: list[dict[str, str]], **kwargs) -> str
    async def stream(self, messages, **kwargs) -> AsyncGenerator[str, None]
    async def embed(self, texts: list[str], **kwargs) -> list[list[float]]
```

三个方法覆盖对话、流式、向量化。`**kwargs` 透传厂商参数（`temperature`、`max_tokens`、`tools` 等），避免接口爆炸。

### 2.2 OpenAI 兼容族

`app/llm/providers/`

| Provider | base_url | 说明 |
|----------|----------|------|
| `OpenAIProvider` | `settings.LLM_BASE_URL` | 基类，`AsyncOpenAI` 客户端 |
| `DeepSeekProvider` | DeepSeek 端点 | 子类，仅设默认 base_url + model |
| `GLMProvider` | 智谱端点 | 同上 |
| `QwenProvider` | DashScope 端点 | 同上 |
| `GeminiProvider` | Gemini 端点 | 同上 |

所有子类都是 OpenAIProvider 的薄包装（~10 行），因为国内主流厂商均提供 OpenAI 兼容 API。**这种薄子类设计是刻意的**：避免在 provider 层引入厂商专属 SDK，统一走 HTTP。代价是非 OpenAI 兼容协议（如原生 Gemini API）无法直接接入，需要重写 provider。

### 2.3 Embedding 解耦

`OpenAIProvider.embed` 使用**独立的** `EMBEDDING_API_KEY` + `EMBEDDING_BASE_URL`，与对话模型分离。这允许对话用 DeepSeek、Embedding 用 DashScope 的混合部署。

`EmbeddingService`（`app/llm/embedding/embedding_service.py`）在 `embed` 之上封装分批：按 `EMBEDDING_BATCH_SIZE`（默认 10，DashScope 单批上限）切片，避免超限。

### 2.4 动态路由

`app/llm/router/model_router.py`

```python
_PROVIDERS = {"openai": OpenAIProvider, "deepseek": ..., "glm": ..., "qwen": ..., "gemini": ...}

class ModelRouter:
    def get_provider(self, name=None) -> LLMProvider
    def get_chat_llm(self) -> LLMProvider              # 默认 provider，无 fallback
    def get_fallback(self, primary=None) -> FallbackPolicy  # 带 secondary 降级
```

- `DEFAULT_LLM_PROVIDER` 配置默认 provider。
- `FALLBACK_LLM_PROVIDER` 配置降级 provider（留空则无降级）。
- 路由表 `_PROVIDERS` 是模块级常量，新增 provider 只需注册一行。

### 2.5 降级切换

`app/llm/router/fallback.py`

`FallbackPolicy` 包装 primary + secondary，逐个尝试，捕获异常后切换：

```python
for attempt in range(max_retries + 1):
    for p in [primary, secondary]:
        try:
            return await p.generate(messages, **kwargs)
        except Exception as e:
            self.failures.append(f"{p.model}:{e}")
            logger.warning("llm_fallback", provider=p.model, error=str(e))
raise last_exc
```

`failures` 列表保留每次失败的 provider+错误，便于审计。`max_retries` 默认 1，避免雪崩。

> **当前接入情况**：`chat.py::_build_runtime` 调 `ModelRouter().get_chat_llm()`（无 fallback）。要走降级链路，应改用 `get_fallback()` 返回的 `FallbackPolicy`——它是 `LLMProvider` 的鸭子类型，可直接传给 Runtime。这是后续优化点。

---

## 3. Tool Registry

### 3.1 Tool 抽象

`app/tools/base.py`

```python
class Tool(ABC):
    name: str
    description: str
    schema: ToolSchema
    permission_scope: str = "default"     # default / read / sensitive
    timeout: float = 30.0
    async def execute(self, **kwargs) -> Any
```

`permission_scope` 是 RBAC 之外的二级权限栅栏：`sensitive` 工具（如 `sql_query`、`file_write`）在生产应配置二次确认。

### 3.2 ToolSchema → OpenAI function 协议

`app/tools/registry/schema.py`

```python
class ToolSchema(BaseModel):
    parameters: list[ToolParameter]
    def to_openai_function(self) -> dict:
        # 转成 {"type":"object","properties":{...},"required":[...]}
```

`ToolRegistry.get_openai_tools()` 把整个注册表转成 OpenAI `tools` 参数，供 ToolNode 直接喂给 LLM。

### 3.3 内置工具

| 工具 | 文件 | permission_scope | 说明 |
|------|------|-----------------|------|
| `knowledge_search` | `builtin/knowledge_tool.py` | read | 调 RAGService 检索知识库 |
| `calculator` | `builtin/calculator_tool.py` | default | 白名单字符数学计算 |
| `web_search` | `builtin/search_tool.py` | default | DuckDuckGo 搜索 |
| `sql_query` | `builtin/sql_tool.py` | sensitive | 只读 SELECT，禁 DDL/DML |
| `file_read` / `file_write` | `builtin/file_tool.py` | read / sensitive | 沙箱目录读写 |

`calculator` 的安全策略：正则白名单 `^[0-9+\-*/().% ]+$`，杜绝 `eval` 注入。`sql_query` 强制 `SELECT` 前缀 + 关键词黑名单（`DROP/DELETE/UPDATE/INSERT/ALTER`）。

### 3.4 注册时机

`chat.py::_build_runtime` 每次请求构造 runtime 时注册工具，但**先检查 `registry.get(name) is None`** 避免重复注册（registry 是模块级单例）。`admin.py::_build_full_registry` 为 `/admin/tools` 端点单独构造一个独立 registry，列出所有内置工具的 schema（不执行）。

> **本次修复**：`admin.py::_build_full_registry` 之前漏注册 `KnowledgeTool`，导致 `/admin/tools` 与实际 runtime 注册表不一致。已补齐（`KnowledgeTool(rag_service=None)`，仅读取类级元数据）。

---

## 4. MCP 接入体系

`app/tools/mcp/client.py`

`MCPClient` 实现 Model Context Protocol 的最小客户端：通过 HTTP/JSON-RPC 与 MCP Server 通信，支持 `tools/list` 与 `tools/call`。

```python
class MCPClient:
    def __init__(self, server_url: str | None = None, timeout: float = 30.0)
    def available(self) -> bool                      # server_url 是否配置
    async def list_tools(self) -> list[MCPTool]
    async def call_tool(self, name, arguments) -> Any
```

**降级设计**：`server_url` 未配置时 `list_tools` 返回 `[]`、`call_tool` 返回 `{"error": "MCP server not configured"}`，保证调用方链路不阻塞。这让 MCP 成为"可选增强"而非"必选依赖"。

> **本次修复**：`app/tools/mcp/__init__.py` 之前为空，`from app.tools.mcp import MCPClient` 会失败。已补齐导出。

### 4.1 接入方式（待落地）

当前 `MCPClient` 已实现但**未接入 ToolRegistry**。规划的接入路径：

1. 启动时（或首次请求时）调 `MCPClient.list_tools()` 拉取远端工具列表。
2. 为每个 `MCPTool` 生成一个 `Tool` 适配器，`execute` 内部调 `MCPClient.call_tool`。
3. `registry.register(adapter)` 注册，对 Runtime 透明。

这一步未实现，是后续工作。文档先行是为了让能力层的接入点可预期。

---

## 5. 能力编排：Runtime 如何消费能力层

```
AgentRuntime
   ├── llm: LLMProvider          ← ModelRouter.get_chat_llm()
   ├── memory_manager: MemoryService
   ├── rag_service: RAGService    ← 内含 LLMProvider (embed) + Retriever
   └── tool_registry: ToolRegistry ← 启动时注册内置工具 + (规划) MCP 适配器
```

Runtime 不直接 new 任何 provider/tool，全部由 `chat.py::_build_runtime` 装配。这让 Runtime 可被单测（注入 stub LLM / stub registry）。

---

## 6. 当前限制

1. **Fallback 未接入主链路**:**已解除**(Phase 4)。`_build_runtime` 改用 `get_fallback()` 返回 `FallbackPolicy`(LLMProvider 鸭子类型),Runtime 无感知。`FALLBACK_LLM_PROVIDER` 未配置时 `get_fallback()` 返回单 primary 包装,行为等价 `get_chat_llm()`。
2. **MCP 适配器未实现**:**已解除**(Phase 8)。`MCPToolAdapter`(`app/tools/mcp/adapter.py`)适配进 registry,启动 lifespan 自动注册(`_register_mcp_tools`),`MCP_SERVER_URL` 未配置时跳过。敏感工具二次确认机制同步落地(`TOOL_CONFIRM_REQUIRED` 事件 + `pending_tool_calls` 暂挂 + 超时跳过)。
3. **ToolNode 绕过 LLMProvider**:**已解除**(Phase 4)。见 [adr/0006-llmprovider-default-not-implemented.md](../adr/0006-llmprovider-default-not-implemented.md)。
4. **Provider 子类无差异**:5 个 provider 行为完全相同,仅默认 base_url 不同。若厂商出现 API 差异(如 Gemini 的 `tools` 格式不同),子类需重写方法--目前未覆盖。