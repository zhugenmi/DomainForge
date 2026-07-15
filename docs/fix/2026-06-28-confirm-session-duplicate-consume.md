# confirm 重复消费导致 410 与潜在 chunks 重复插入

## 现象

用户上传两份法律文档，导入到接近完成时，后端日志显示：

```
INFO: POST /api/v1/knowledge/confirm HTTP/1.1 410 Gone
INFO: POST /api/v1/knowledge/confirm HTTP/1.1 410 Gone
```

但数据库中劳动合同法 125 条 chunks 已全部 `INSERT` + `status='indexed'` + `COMMIT`，导入实际**成功**。410 来自后续的重复 `confirm` 请求——session 已被消费/清理，重复请求拿不到。

## 根因

`app/api/knowledge.py` 的 `confirm_import` 与后台 `_run_import` 之间存在**消费时机错位**的竞态：

1. `confirm_import` 用 `preview_store.get(session_id)` 仅做**校验**，不消费。
2. session 的 `remove` 推迟到 `_run_import` 末尾（整个 embed + 持久化跑完之后）才执行。
3. 在 import 进行期间，session 仍在 store 中，重复的 `confirm` 仍能 `get` 成功。

这带来两个后果：

- **良性情况**（本次现象）：重复 confirm 发生在 import **完成之后**，session 已 remove → 返回 410。导入数据本身正确，只是日志噪声 + 用户看到 410 误以为失败。
- **恶性情况**（潜在隐患）：重复 confirm 发生在 import **进行中**，session 还在 → 通过校验，`create_task` 再起一个 `_run_import`，**重复 INSERT chunks**，造成脏数据。前端 ImportModal 的轮询循环、用户双击确认按钮、网络重试都可能触发。

本质：session 被当作"校验令牌"而非"一次性消费凭证"，校验与消费分离，留下窗口。

## 解决办法

在 `confirm_import` 中**原子消费** session——`get` 校验通过后立即 `remove`，把数据副本交给后台任务，后台任务不再依赖 session：

```python
data = await preview_store.get(req.session_id)
if data is None:
    raise HTTPException(status_code=410, detail="preview session expired or not found")
# 原子消费：立即 remove，避免并发/重复 confirm 在 import 进行中读到同一 session
await preview_store.remove(req.session_id)

job = await import_job_store.create(...)
payload = {"domain": data["domain"], "chunk_strategy": data["chunk_strategy"], "files": data["files"]}
asyncio.create_task(_run_import(job.job_id, payload))
```

对应改动：

1. `confirm_import`：`get` 后立即 `remove`，消费时机提前到请求入口。
2. `_run_import`：签名去掉 `session_id` 参数；末尾删掉 `await preview_store.remove(session_id)`（已在入口消费）。
3. payload 在 confirm 处即构造为独立副本（原代码已是字典浅拷贝，行为不变）。

修复后行为：

- 重复 confirm 在入口即被挡掉返回 410，session 不再暴露在 import 进行期间。
- 消除"进行中重复 confirm → 重复 job → 重复插入 chunks"的竞态窗口。
- import 失败时 session 已消费，用户需重新上传预览——符合预期（一次性凭证语义），且 import 失败本就回滚无副作用。

## 验证

- `tests/api/test_knowledge.py` 11 passed。
- `test_confirm_import_persists_documents_and_chunks`：单次 confirm 正常导入。
- `test_confirm_expired_session_returns_410`：session 不存在时 410（行为不变）。
- `test_legal_import_persists_chapter_and_article_metadata`：metadata 链路不受影响。
