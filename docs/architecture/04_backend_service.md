# 04 后端服务架构:RESTful + SSE + Redis + 安全层

> 版本：0.1.0 | 日期：2026-06-17 | 对应代码：`app/api/`、`app/main.py`、`app/services/`、`app/security/`

---

## 1. 设计目标

提供稳定的 HTTP 接口、可流式输出的 Agent 思考链路、以及高并发下的会话/缓存/限流能力。本章**如实区分已实现与规划**，避免文档与代码脱节。

---

## 2. 应用骨架

`app/main.py`

```python
@asynccontextmanager
async def lifespan(app):
    setup_logging()
    sweep_task = asyncio.create_task(run_periodic_sweep(interval=60))   # 预览会话清理
    yield
    sweep_task.cancel()

app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", ...], ...)
app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
# ...共 8 个 router
```

- **lifespan**：启动时初始化日志、起预览会话清扫后台任务；关闭时取消。
- **CORS**：允许前端 dev origin（3000）+ 通配，便于本地联调。生产应收紧。
- **统一前缀**：所有 router 挂 `/api/v1`，便于版本演进。

---

## 3. RESTful API 全景

| Router | 前缀 | 端点 |
|--------|------|------|
| health | — | `GET /health` |
| chat | `/chat` | `POST /chat`、`GET /chat/stream` |
| knowledge | `/knowledge` | `POST /index`、`GET /categories`、`POST /categories`、`GET /categories/{domain}/documents`、`POST /upload`、`POST /confirm`、`DELETE /documents/{id}`、`GET /search` |
| sessions | `/sessions` | `GET /`、`GET /{id}`、`GET /{id}/messages`、`DELETE /{id}` |
| audit | `/audit` | `GET /{trace_id}`、`GET /` |
| evals | `/evals` | `POST /run`、`GET /results` |
| admin | `/admin` | `GET /tools`、`GET /metrics`、`GET /health/detail` |
| auth | `/auth` | `POST /login`、`GET /me`、`GET /admin-only` |

完整请求/响应结构见 `docs/api_reference.md`。

### 3.1 两阶段知识库导入

`/knowledge/upload` + `/knowledge/confirm` 是设计上的刻意拆分：

1. **upload**：多文件上传 → 解析 + 切块 → 返回预览（**不 embed**，不落库）。存入 `PreviewStore`（进程内，TTL `PREVIEW_SESSION_TTL=600s`）。
2. **confirm**：用户确认/编辑后 → embed + 持久化到 `document_chunks`。

理由：embed 是昂贵操作（远程 API 调用），让用户先看到分块效果再决定是否入库，避免错配后重复 embed。`run_periodic_sweep` 每 60s 清扫过期预览会话，防止内存泄漏。

### 3.2 会话管理

`/chat` 与 `/chat/stream` 的会话逻辑：

- `session_id` 为空 → 自动创建会话（用默认用户）。
- `session_id` 不存在 → 也创建新会话（容错）。
- 用户消息与助手回复均落 `messages` 表，供 `/sessions/{id}/messages` 回放。

---

## 4. SSE 流式输出

`app/api/chat.py::chat_stream` + `app/runtime/events/event_bus.py`

```python
@router.get("/stream")
async def chat_stream(query, session_id=None, db=Depends(get_db)):
    ...
    runtime = await _build_runtime(db, session_id, user_id=user.id)
    state = AgentState(query=query)

    async def _stream():
        try:
            with request_trace("chat_stream", session_id=str(session_id)) as span:
                await audit.log(span.trace_id, "chat_stream_request", {...})
                async for chunk in runtime.run_stream(state):
                    yield chunk                      # 已是 "data: {...}\n\n"
        except Exception as e:
            yield f'data: {{"event":"error","data":{{"message":"{e}"}}}}\n\n'
        finally:
            await message_repo.create(session_id, "assistant", state.final_answer or "[生成失败]")
            await db.commit()

    return StreamingResponse(_stream(), media_type="text/event-stream")
```

**关键设计**：

- **trace 贯穿**：`request_trace` 开启新 trace，`span.trace_id` 写入审计日志，可串起整条链路。
- **错误降级**：`run_stream` 内部异常转成 `error` SSE 事件，连接不中断。
- **持久化兜底**：`finally` 中无论成功失败都写一条 assistant 消息（失败时写 `[生成失败]`），保证会话历史完整。
- **commit 容错**：`db.commit()` 失败则 rollback，避免污染会话。

SSE 事件类型见 `app/runtime/events/event_type.py`，前端按 `event` 字段分发渲染（intent / plan / retrieval / tool / reflection / final_answer / error）。

---

## 5. Redis 接入(Phase 6 已落地)

**状态**:已接入。`app/services/redis.py::get_redis()` 返回 `Redis | None`--`REDIS_ENABLED=false` 或 ping 失败时返回 `None`,消费点检查 `None` 即跳过。这是降级的统一信号。全链路优雅降级:Redis 不可用时,所有消费点 no-op 退化为原有行为(无缓存/无限流/进程内存储),业务不阻塞。

| 能力 | 实现 | 说明 |
|---|---|---|
| Prompt 响应缓存 | `app/api/chat.py::_try_cache` / `_maybe_cache` | key = `(session_id, query)`,仅缓存 `intent=chat` 的简单问答,TTL 10min;知识库 confirm/delete 时 `cache_clear_prefix("chat:")` |
| 请求限流 | `app/api/middleware/rate_limit.py::RateLimitMiddleware` | 路由组滑动窗口(Redis ZSET),`/chat` 20 req/min、`/knowledge/search` 60 req/min;429 + Retry-After |
| PreviewStore 跨实例共享 | `app/services/preview_store.py` | Redis hash + TTL,进程内 dict 作退路;多 worker 共享预览会话 |
| 检索结果缓存 | `app/rag/service.py::RAGService.search` | key = `(mode, top_k, domain, query)`,TTL 15min;知识库 confirm/delete 时 `cache_clear_prefix("rag:")` |

**缓存工具**(`app/services/cache.py`):`cache_get(namespace, *parts)` / `cache_set(namespace, value, ttl, *parts)` / `cache_clear_prefix(prefix)`。key 生成 `{namespace}:{sha256(":".join(parts))[:16]}`,全异常吞掉(失败 log warning 返回 None/no-op),消费点无需 try/except。

**限流 identifier 优先级**:已认证用户 `u:{sub}` > IP(`X-Forwarded-For` 首段 > `request.client.host`)。未登录用户才用 IP,避免公司出口 IP 共享误伤。

**优雅关机**(`app/main.py::lifespan`):`yield` 后 cancel 后台清扫任务 + `await sweep_task`(等 CancelledError 避免任务泄漏)+ `close_redis()`。in-flight 请求等待由 uvicorn `--timeout-graceful-shutdown` 控制(部署配置项,非应用层)。
---

## 6. 安全层

`app/security/`

| 模块 | 职责 |
|------|------|
| `jwt.py` | `create_token` / `get_current_user`，HS256，`JWT_SECRET` 签名 |
| `auth.py` | `/auth/login`（dev 任意用户名可登录，`ADMIN_API_KEY` 校验升 admin）、`/auth/me`、`/auth/admin-only` |
| `permission.py` | `Role` 枚举（user/admin）、`require_role(...)` 依赖注入 |
| `prompt_guard.py` | `check_prompt(query)` 检测 Prompt 注入，命中则拒绝并写审计 |
| `content_filter.py` | 内容过滤（敏感词/违规） |

`chat.py::_guard` 在 `/chat` 与 `/chat/stream` 入口调 `check_prompt`，命中注入特征返回 `"已拒绝处理疑似 Prompt 注入的输入"`，不进入 Runtime。

> **已知弱点**：`JWT_SECRET` 默认 `"change-me-in-production"`，dev 环境硬编码。生产必须通过 env 覆盖。HMAC key 长度告警（23 字节 < 32）已在测试日志出现，生产应换 32+ 字节随机串。

---

## 7. 数据库与会话

`app/database/`

- **session.py**：`async_sessionmaker` + `get_db` 依赖注入，每个请求一个 `AsyncSession`。
- **base.py**：`Base = DeclarativeBase`（本次清理删除了未被引用的 `TimestampMixin`，各模型自带 id/created_at）。
- **repositories/**：6 个 Repo（user / session / message / document / memory / category），封装 CRUD，API 层不直接写 SQL。

驱动：生产 `asyncpg`（PostgreSQL），测试 `aiosqlite`（内存库）。`bm25.py::_is_postgres` 与 `chunk.py::_vector_type` 据方言切换实现，保证同一套代码两边可跑。

---

## 8. 当前限制

1. **Redis 未接入**:**已解除**(Phase 6)。见 §5,缓存/限流/共享 session/检索缓存均已落地。
2. **无连接池监控**:asyncpg 的池大小、等待时长未暴露指标。
3. **CORS 过宽**:**已解除**(Phase 3)。`CORS_ORIGINS: list[str]` 移除 `"*"` 通配,`@field_validator` 支持逗号分隔 env 解析,生产配具体域名。
4. **无优雅关机**:**已解除**(Phase 6)。lifespan cancel 后台任务 + `await sweep_task` + `close_redis()`;in-flight 请求由 uvicorn `--timeout-graceful-shutdown` 控制。
5. **PreviewStore 单实例**:**已解除**(Phase 6)。Redis hash + TTL 后端,进程内 dict 退路,多 worker 共享。

> **安全加固**(Phase 3):`JWT_SECRET` 在 `APP_ENV=prod` 模式强制 ≥32 字节且非默认值(`model_validator`);密码哈希用 PBKDF2-SHA256 600k 迭代(见 [adr/0003-pbkdf2-over-bcrypt.md](../adr/0003-pbkdf2-over-bcrypt.md));`/auth/login` prod 模式校验密码,admin 统一由 `ADMIN_API_KEY` 决定;login/logout/敏感操作落审计(含 ip/ua,不记密码)。