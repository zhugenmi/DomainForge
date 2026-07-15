# 流式响应 Cancel 导致助手消息丢失 + 测试 event loop 污染 + 检索分数污染 ORM

## 问题现象

前端流式聊天测试时，后端日志在 `chat_stream` span 结束后抛出：

```
Exception terminating connection <AdaptedConnection <asyncpg.connection.Connection object at ...>>
...
asyncio.exceptions.CancelledError: Cancelled via cancel scope ... by <Task pending name='starlette.middleware.base.BaseHTTPMiddleware.__call__.<locals>.call_next.<locals>.coro' ...>
```

同时观察到 `UPDATE document_chunks SET score=0.0` 被执行，且助手回复未保存到 `messages` 表。

## 根因分析

三个独立问题叠加放大。

### 1. `BaseHTTPMiddleware` 与 `StreamingResponse` 的 cancel 传播

`RateLimitMiddleware` 继承 `starlette.middleware.base.BaseHTTPMiddleware`。Starlette 的 `BaseHTTPMiddleware` 在 `call_next` 内部会启动一个独立 task 来消费响应体，流式响应（`StreamingResponse`）结束时该 task 被取消。cancel 信号沿调用链传播进端点生成器的 `finally` 块：

- `app/api/chat.py` 的 `_stream()` 在 `finally` 里执行 `db.commit()` 保存助手消息
- cancel 在 commit 进行中触发 → asyncpg 连接被异常终止 → 抛 `CancelledError`
- `CancelledError` 是 `BaseException`（Python 3.8+），`except Exception` 抓不到，`finally` 里的 `db.rollback()` 也无法执行
- 结果：助手消息丢失，连接 32 秒后才被池清理逻辑 `ROLLBACK`

### 2. 测试 event loop 污染

全量跑 `tests/api/` 时，11 个测试报 `RuntimeError: There is no current event loop`，但单独跑各文件均通过。

- `tests/api/test_knowledge.py`、`test_sessions_messages.py` 使用 `asyncio.new_event_loop()` + `loop.close()`
- 其它文件（`test_new_apis.py`、`test_session_agent.py` 等）使用 `asyncio.get_event_loop().run_until_complete(...)`
- Python 3.12 下，关闭的 loop 残留在线程 event loop policy 中，后续测试 `get_event_loop()` 拿到已关闭的 loop，`run_until_complete()` 抛 `RuntimeError`

污染顺序：`test_knowledge`（用 `new_event_loop+close`）排在 `test_new_apis` 之前，前者关闭 loop 后污染后者。

### 3. 检索分数污染 ORM 托管对象

`document_chunks.score` 是 DB 列（`Float, nullable=True`）。检索路径把临时检索分数写到该列：

- `app/rag/retrieval/bm25.py:157` — `_search_fallback` 把 BM25 分数写到从 DB 查出的 session 托管 `DocumentChunk` 对象
- `app/rag/retrieval/hybrid.py:72` — rerank 后把分数写到候选 chunk 对象
- `app/database/repositories/document_repo.py` 的 `vector_search` / `list_chunks_by_domain` 返回的 `DocumentChunk` 是 session 托管对象
- 写 `score` 后对象变 dirty → `chat_stream` 的 `finally` 里 `db.commit()` 把临时分数 flush 进 DB（日志里的 `UPDATE document_chunks SET score=0.0`）

与问题 1 叠加：commit 被取消时，score 更新也已发出但事务回滚，连接被终止。

## 修复

### 修复 1：`RateLimitMiddleware` 改为纯 ASGI middleware

`app/api/middleware/rate_limit.py` 从 `BaseHTTPMiddleware` 子类改写为纯 ASGI middleware：

- `dispatch(request, call_next)` → `__call__(scope, receive, send)`
- 从 `scope["path"]` / `scope["headers"]` 直接读路径与 `x-forwarded-for`，无需构造 `Request`
- 429 响应直接 `send` ASGI 事件（`http.response.start` + `http.response.body`）
- 非限流请求直接 `await self.app(scope, receive, send)` 透传，响应体不再被中间件后台 task 消费 → 流式响应结束时不 cancel 调用链 → `finally` 的 `db.commit()` 不被打断

纯 ASGI middleware 是 Starlette 官方对 streaming 场景的推荐做法。

### 修复 2：测试统一用 `asyncio.run`

涉及文件：`tests/api/test_knowledge.py`、`test_sessions_messages.py`、`test_new_apis.py`、`test_session_agent.py`、`test_agents_api.py`、`test_auth_hardening.py`、`test_chat_enhancements.py`、`test_chat_agent_binding.py`、`test_backend_redis.py`。

- `asyncio.get_event_loop().run_until_complete(x)` → `asyncio.run(x)`
- `loop = asyncio.new_event_loop(); loop.run_until_complete(x); loop.close()` → `asyncio.run(x)`

`asyncio.run` 每次创建全新 loop 并在结束时彻底清理，不污染线程 event loop policy 状态。

另外 `tests/api/test_chat_agent_binding.py::test_chat_with_agent_id_injects_system_prompt` 的 flaky 断言：`_StubLLM` 用单一 `captured["system"]` 覆盖，chat 流程多次调用 LLM（意图识别/生成/质量评估），最终保存的是最后一次调用的 prompt 而非带 agent system_prompt 的那次。改为收集所有调用的 system prompt 列表，断言"任意一次调用包含 agent system_prompt"。

### 修复 3：检索结果从 session 分离

`app/rag/retrieval/bm25.py` 的 `_search_fallback` 和 `app/rag/retrieval/vector.py` 的 `search` 在返回前对每个 chunk 调用 `self.db.expunge(c)`：

- 检索结果是只读快照，从 session identity map 移除后变为 detached 对象
- 后续写 `score`（BM25 分数 / rerank 分数）不被 dirty tracking 跟踪 → `db.commit()` 不再持久化临时分数
- `_search_pg` 路径本来就用 `DocumentChunk(...)` 新建 transient 对象，不受影响

新增回归测试 `tests/rag/test_retrieval_score_pollution.py`：检索后断言 `db.dirty` 中无 `DocumentChunk`。

## 验证

- `tests/api/test_backend_redis.py`（限流专项）11 passed
- `tests/api/test_chat_enhancements.py`（流式 chat）7 passed
- 全量 `tests/api/`：74 passed（修复前 62 passed + 1 failed + 11 errors）
- 全量 `tests/`：**345 passed, 0 failed**

## 附：ReAct 循环 stub 重复执行 tool_call

`tests/runtime/test_tools_mcp.py::test_sensitive_tool_resumes_after_confirm` 失败：`assert len(state.tool_results) == 1` 实际为 4。

**根因**：`9cd44ef "improve tool module"` 把 `ToolNode.execute` 从单次执行改成 ReAct 循环（`for iteration in range(state.max_tool_iterations)`），每轮调用 `chat_with_tools`。测试 stub `_ToolCapableProvider.chat_with_tools` 每次返回同一份 `tool_calls`，循环把工具执行了 `max_tool_iterations`（4）次。产品代码正确（真实 LLM 拿到工具结果后会停止发 tool_call），stub 过时。

**修复**：stub 首次返回 `tool_calls` 后清空，模拟真实 LLM 在工具执行后转入 finalize。对比 `test_sensitive_tool_resumes_from_pending`（预设 `pending_tool_calls`，第一轮不调用 `chat_with_tools`）不受影响。

## 教训

- `BaseHTTPMiddleware` 不适合需要流式响应的中间件，纯 ASGI 更安全
- `asyncio.get_event_loop()` 在 Python 3.12 已 deprecated 且易跨测试污染，统一用 `asyncio.run`
- 检索层返回 ORM 托管对象时，任何属性写入都会被 dirty tracking；只读快照应 `expunge`
