# ADR 0004:知识库导入用异步任务队列而非同步阻塞

> 状态:已采纳 | 日期:2026-06-28

## 背景

`POST /knowledge/confirm` 原同步跑完整个 embed + persist 循环。导入《民法典》(1322 chunks)时,即使加了 429 退避+节流,总耗时仍轻易超过前端代理 60s 超时 -> `socket hang up`。但后端 embedding 循环仍在跑,客户端看不到结果,DB 最终 ROLLBACK,文档卡 `parsing`。光靠重试解决不了--账户级限额恢复需要分钟级。

## 决策

`confirm_import` 改为 `202 {job_id, status:"pending"}` 立即返回,后台 `_run_import` 用独立 `async_session_factory` 跑 embed + persist,前端轮询 `GET /knowledge/import/{job_id}/status` 获取进度。

## 理由

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| 同步 + 加长超时 | 前端代理/浏览器 60s 上限难突破;同步阻塞占用 worker,高并发下 worker 耗尽 |
| 同步 + 分批 confirm | 用户需多次点击,体验差;每批仍可能超时 |
| Celery/RQ 等外部任务队列 | 引入 Redis broker + worker 进程,运维复杂度上升;单 worker 部署用不上 |

### 选进程内异步任务的理由

1. **API 契约清晰**:202 + job_id 是 HTTP 标准的"已接受、处理中"语义,前端天然支持轮询。
2. **进度可视化**:`ImportJobStatus` 含 `processed_chunks / total_chunks`,前端展示分块级进度条,用户感知"在跑"而非"卡死"。
3. **无新依赖**:`asyncio.create_task` + 进程内 `ImportJobStore`(dict + Lock),单 worker 部署足够。
4. **失败可观测**:job 标 `failed` + 记录 error,用户明确看到失败原因,而非 500 后茫然。
5. **与 PreviewStore 同模式**:PreviewStore 也是进程内 store + TTL 清扫,技术栈一致。

## 后果

- **正面**:导入不再超时;进度可视化;失败可观测;无新依赖。
- **负面**:`ImportJobStore` 进程内,多 worker 部署下 job 状态不共享--已知技术债,需迁移 Redis(与 `preview_store` 同模式)。
- **测试 gotcha**:stub `OpenAIProvider` 时必须同时 patch `app.api.knowledge` 模块绑定(它用 `from ... import OpenAIProvider` 绑了自己的名字),否则后台任务打真实 API。异步轮询测试用 `httpx.ASGITransport` + `await asyncio.sleep` 让后台任务在同 loop 推进;`TestClient` 同步 portal 的 `time.sleep` 会让后台任务饿死。
- **迁移成本**:多 worker 部署时,`ImportJobStore` 迁 Redis hash + TTL,接口不变。
