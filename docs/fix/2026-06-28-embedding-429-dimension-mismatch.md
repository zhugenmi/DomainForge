# Embedding 429 限流与维度不匹配导致导入 500

> 日期:2026-06-28
> 类型:生产事故 + 配置错误
> 影响范围:`app/llm/embedding/embedding_service.py`、`app/llm/providers/openai.py`、`app/api/knowledge.py::confirm_import`

## 1. 问题现象

用户导入《民法典》docx 时连续 500。错误日志:

```
openai.RateLimitError: Error code: 429 - {'error': {'code': 'AccountRateLimitExceeded',
  'message': 'Requests are too frequent...'}}}
```

后端 `confirm_import` 500 -> DB ROLLBACK -> 文档卡在 `parsing` 状态。修复限流后立即暴露第二个错误:

```
ValueError: expected 1024 dimensions, not 2048
```

## 2. 根因分析

两个独立问题叠加,先 429 后维度不匹配。

### 2.1 EmbeddingService 无限流无重试

`EmbeddingService.embed` 在 `for i in range(0, len(texts), self.batch_size)` 循环里连续发射 132 个批次请求(民法典 1322 chunks),**无批次间隔、无 429 重试**。火山方舟账户级 RPM 被打穿 -> 429 -> confirm_import 500 -> DB ROLLBACK -> 文档卡 parsing。

### 2.2 配置与模型输出维度不匹配

维度报错根因:火山方舟 `doubao-embedding-vision` 是视觉多模态模型,默认输出 2048 维,而 DB 列 `document_chunks.embedding` 是 `Vector(1024)`。切换到阿里云 `text-embedding-v3` 后仍报 2048--因为 `.env` 的 `EMBEDDING_BASE_URL` 是占位符 `{WorkspaceId}`,且改配置后服务未重启,进程仍用旧火山方舟配置。

**两层根因**:
1. `.env` 占位符未替换为真实端点
2. `OpenAIProvider.embed` 未显式传 `dimensions` 参数,模型用默认输出维度(2048),与 DB 列(1024)不一致

## 3. 解决方案

### 3.1 EmbeddingService 加指数退避 + 批次节流

```python
async def _embed_with_retry(self, batch: list[str]) -> list[list[float]]:
    attempt = 0
    while True:
        try:
            return await self.llm.embed(batch)
        except RateLimitError as e:
            if attempt >= self.max_retries:
                raise
            retry_after = getattr(e, "retry_after", None)
            wait = float(retry_after) if retry_after else _BASE_BACKOFF * (2 ** attempt)
            await asyncio.sleep(wait)
            attempt += 1
```

- **指数退避**:`2^n × base`(默认 base=1s,最多 4 次),优先尊重 `Retry-After` header
- **批次节流**:`settings.EMBEDDING_BATCH_INTERVAL`(默认 0.2s),批次间 `await asyncio.sleep`,避免连续请求触发账户级 RPM
- **进度回调**:`embed(texts, on_progress=...)` 可选回调,每批后调用 `(done, total)`,供异步导入任务上报 chunk 级进度

### 3.2 .env 端点替换 + 显式传 dimensions

1. `.env`:`EMBEDDING_BASE_URL` 占位符 -> 真实 DashScope 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`
2. `OpenAIProvider.embed` 显式传 `dimensions=settings.EMBEDDING_DIMENSION`:

```python
create_kwargs: dict = {"model": ..., "input": texts}
if settings.EMBEDDING_DIMENSION:
    create_kwargs["dimensions"] = settings.EMBEDDING_DIMENSION
response = await embed_client.embeddings.create(**create_kwargs)
```

`text-embedding-v3` 支持 `dimensions` 参数(64/128/256/512/768/1024),显式传 1024 硬保证输出维度与 DB 列一致。不支持该参数的模型会忽略。

## 4. 验证

- `tests/llm/test_embedding_service.py`:429 重试(成功路径 + 重试上限放弃)、批次节流。
- 真实导入《民法典》1322 chunks 成功,无 429,无维度报错。
- DB 列 `embedding` 维度稳定 1024。

## 5. 复盘

- **教训:配置改了必须重启 uvicorn**(`.env` 启动时加载)。能返回 2048 说明走的是旧配置,而非新模型。调试时先 `print(settings.EMBEDDING_BASE_URL)` 确认运行时配置,再排查模型行为。
- **预防**:远程 API 调用必须有限流(批次间隔)+ 重试(指数退避 + 尊重 Retry-After),否则账户级限额一旦打穿,重试本身又加重压力,形成雪崩。`EmbeddingService` 是模板,后续 LLM 调用、rerank 调用同理。
- **预防**:DB 列维度与模型输出维度必须显式对齐--要么 DB 列跟随模型默认维度,要么调用时显式传 `dimensions` 硬约束。后者更稳(不依赖模型默认值)。
