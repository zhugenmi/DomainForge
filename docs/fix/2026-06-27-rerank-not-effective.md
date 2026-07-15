# Rerank 实际未生效:三个叠加 bug

> 日期:2026-06-27(初版修复)/ 2026-06-30(二次修复 DashScope 请求体格式)
> 类型:功能静默失效
> 影响范围:`app/llm/rerank/` 整条 rerank 链路;检索精度退化

## 1. 问题现象

日志持续输出 `rerank_noop reason=no_rerank_endpoint`,rerank 走关键词重叠退路(`rerank_simple`),真实 BGE/DashScope rerank API 从未调用。检索结果排序依赖关键词重叠,精度远低于预期。

## 2. 根因分析

三个 bug 叠加,任何单一修复都无法让真实 rerank 生效。

### 2.1 `BGEReranker.model` 默认值 truthy 导致环境变量被忽略

`app/llm/rerank/bge_reranker.py`:

```python
class BGEReranker:
    def __init__(self, model: str = "bge-reranker-base", ...):
        self.model = model or os.getenv("RERANK_MODEL")
```

`model` 默认值 `"bge-reranker-base"` 是 truthy,`model or os.getenv(...)` 永远走默认值,**环境变量 `RERANK_MODEL` 从未被读取**。

### 2.2 `RERANK_MODEL` 未在 Settings 登记

`app/configs/settings.py` 未声明 `RERANK_MODEL` 字段。pydantic-settings 2.14.1 默认 `extra="forbid"`,在 `.env` 填 `RERANK_MODEL=qwen3-rerank` 后启动直接报错 `extra fields not permitted`。

用户要么不填(走 2.1 的默认值 bug),要么填了启动失败--两条路都走不通。

### 2.3 DashScope rerank 端点与 BGE 兼容格式完全不兼容

配置 `RERANK_BASE_URL=https://dashscope.aliyuncs.com/...` 后,`bge_reranker.py` 仍按 BGE 兼容格式构造请求:
- URL: `{base}/rerank` -> DashScope 上 404
- 请求体: 平铺 `{model, query, documents, top_n}` -> DashScope 原生端点要求嵌套 `{model, input:{query,documents}, parameters:{top_n}}` -> 400 `Field required: input.query`

### 2.4 二次发现(2026-06-30):嵌套体也不对

§2.3 的初版修复按 DashScope 文档发嵌套体,但实测 `qwen3-rerank` 原生端点要求**扁平请求体**(`{model, query, documents, top_n}` 在顶层),嵌套体被拒为 400 `Field required: input.query`。文档与实际行为不一致。

## 3. 解决方案

### 3.1 model 默认值改 None

```python
class BGEReranker:
    def __init__(self, model: str | None = None, ...):
        self.model = model or os.getenv("RERANK_MODEL")
```

`None or os.getenv(...)` 正确读取环境变量。

### 3.2 Settings 登记三个 rerank 字段

`app/configs/settings.py` 新增:
```python
RERANK_BASE_URL: str = ""
RERANK_API_KEY: str = ""
RERANK_MODEL: str = ""
```

### 3.3 新建 QwenReranker 走 DashScope 扁平体原生端点

不动 `bge_reranker.py`(生产 BGE 兼容后端仍依赖它),新建 `app/llm/rerank/qwen_reranker.py` 专走扁平体原生端点:

```python
class QwenReranker:
    # URL: DashScope 原生 /api/v1/services/rerank/text-rerank/text-rerank
    # 请求体: 扁平 {model, query, documents, top_n}
    # 响应: output.results[].relevance_score
```

`rerank_service.py` 新增 `_select_default_reranker()`:按 `settings.RERANK_MODEL` 名字分发--含 `qwen` 走 `QwenReranker`,否则走 `BGEReranker`。`RerankService()` 无参构造即自动选对实现,调用方无需感知。

### 3.4 hybrid.py 用 index 回填 chunk

`app/rag/retrieval/hybrid.py` 原先用 `c.content == cand.text` 文本匹配回填 chunk,重复 chunk 会互相吃掉。改用 `RerankCandidate.index`(候选在原列表中的下标)直接回填 `candidates[cand.index]`。

## 4. 验证

- 真实 DashScope `qwen3-rerank` 调用成功,日志 `rerank_real candidates=20`(而非 `rerank_noop`)。
- 查询"合同的违约责任" -> 违约条款 0.82、民法总则 0.33、基金 0.32,排序正确。
- `tests/llm/test_rerank.py` 覆盖:model None 读取 env、QwenReranker 扁平体构造、index 回填。

## 5. 复盘

- **触发条件**:配置项链路有多处独立 bug 时,任何单一修复都无效,需全链路排查。本例中"默认值 truthy" + "settings 未登记" + "端点格式不兼容"三者叠加,孤立看每个都不致命,组合后表现为"rerank 静默退化为关键词重叠"。
- **预防**:
  - 默认值用 `None` 而非 truthy 占位符,让 `or` fallback 链可生效。
  - 所有 env 变量必须在 Settings 登记,`extra="forbid"` 是防线不是障碍。
  - 第三方 API 集成必须有真实调用测试,不能只测 stub。
- **教训**:文档与实际行为不一致是常态。DashScope 文档写嵌套体,实际要扁平体--以实测为准,不迷信文档。
