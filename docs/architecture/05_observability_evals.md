# 05 可观测性与评测:Tracing + Metrics + Evals 闭环

> 版本:0.2.0 | 日期:2026-06-27(OTel 迁移后) | 对应代码:`app/observability/`、`app/evals/`

---

## 1. 设计目标

让 Agent 的每一次执行都可追溯、可度量、可回归。具体三件事:

1. **Tracing**:一次请求从 API 到 LLM/Tool/RAG 的完整链路可串起来。
2. **Metrics**:关键计数与延迟可量化、可快照。
3. **Evals**:用固定数据集回归答案质量,bad case 可定位、可闭环。

> **演进状态**:Phase 5 之前为自研轻量 Tracing/Metrics(`contextvars.ContextVar` + structlog + 进程内 dict)。Phase 7 已迁移到 OpenTelemetry SDK,Tracing 可经 OTLP 导到 Jaeger/Tempo,Metrics 镜像到 OTel Counter/Histogram,Evals 新增 LLM-as-judge 语义评分。本章 §2-§4 描述当前实现(OTel + 自研双写),调用方接口(`request_trace`/`span`/`metrics.inc`/`metrics.observe`/`metrics.snapshot`)签名不变,改动收敛在内部实现。

---

## 2. Tracing(OTel SDK + 自研兼容层,Phase 7 迁移)

`app/observability/tracing/tracer.py`

### 2.1 模型

```python
@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str            # uuid4 前 16 位
    parent_id: str          # 嵌套时自动设置
    start_ts: float
    end_ts: float
    attributes: dict
    error: str | None
```

用 `contextvars.ContextVar` 维护两条上下文：

- `_trace_id_var`：当前请求的 trace_id（贯穿整个请求）。
- `_span_stack_var`：当前协程的 span 栈，新 span 自动取栈顶为 parent_id——这是嵌套关系的关键。

### 2.2 两个入口

| 入口 | 行为 | 用途 |
|------|------|------|
| `request_trace(name, **attrs)` | 生成新 trace_id，开启根 span | API 请求入口（`chat.py`） |
| `span(name, **attrs)` | 复用当前 trace_id，开子 span | 内部函数（LLM 调用、tool 执行、检索） |

```python
@contextmanager
def span(name, **attrs):
    tid = _trace_id_var.get() or new_trace_id()
    parent_id = _span_stack_var.get()[-1].span_id if _span_stack_var.get() else ""
    s = Span(name, tid, parent_id=parent_id, start_ts=time.time(), attributes=attrs)
    ...yield s...
    finally:
        s.end_ts = time.time()
        logger.info("span_end", span=s.name, trace_id=s.trace_id,
                    span_id=s.span_id, parent_id=s.parent_id,
                    duration_ms=..., attrs=s.attributes)
```

span 结束时通过 structlog 输出 `span_end` 日志，含 trace_id / span_id / parent_id / duration_ms / attrs——这是当前 tracing 的**日志落地形式**(OTel SDK 接入后,Phase 7,同时经 OTLP 导到 Jaeger/Tempo;span_end 日志保留作日志聚合系统的兼容通路)。

### 2.3 装饰器

`decorators.py::trace(name)` 包装同步/异步函数，自动开 span：

```python
@trace("llm.generate")
async def generate(self, messages, **kwargs): ...
```

自动用 `f"{fn.__module__}.{fn.__qualname__}"` 命名 span，零侵入。

### 2.4 审计联动

`AuditService.log(trace_id, action, payload)` 把关键事件（chat_request / chat_response / chat_stream_request）落 `audit_logs` 表，**用同一个 trace_id 串起**。`/audit/{trace_id}` 端点可查回整条审计链路。

`chat.py` 的实践：

```python
with request_trace("chat", session_id=...) as span:
    await audit.log(span.trace_id, "chat_request", {...})
    state = await runtime.run(state)
    await audit.log(span.trace_id, "chat_response", {"intent": state.intent, ...})
```

trace_id 同时出现在日志（`span_end`）与审计表，是跨系统串联的纽带。

---

## 3. Metrics（进程内计数器+计时器）

`app/observability/metrics/metrics.py`

`_Metrics` 单例（`metrics`）：

| 方法 | 用途 |
|------|------|
| `inc(name, value=1.0)` | 计数器（线程安全，`threading.Lock`） |
| `observe(name, seconds)` | 计时器记录（秒入，内部转 ms） |
| `time(name)` 上下文管理器 | 自动计时代码块 |
| `snapshot()` | 导出 `{counters: {...}, timers: {name: {count, avg_ms, p50_ms, max_ms}}}` |
| `reset()` | 测试用，清零 |

timer 保留最近 1024 个样本，超限裁剪到 512——滚动窗口，避免内存无限增长。`snapshot` 计算平均、p50、max，不存全量。

**消费点**：

- `/admin/metrics` 端点返回 `metrics.snapshot()`。
- `IndexingPipeline.index_text` 调 `metrics.inc("indexing.chunks", len(chunks))` 统计入库量。

> 当前 metrics 仅进程内，多 worker 部署下各 worker 独立。要跨实例聚合需接 Prometheus / OTel collector。

---

## 4. Evals 评测体系

`app/evals/`

### 4.1 数据集

`app/evals/datasets/{legal,finance}/*.json`，每条用例：

```json
{
  "id": "legal_001",
  "query": "民法典中民事法律行为的有效条件？",
  "expected_keywords": ["民事法律行为", "有效", "条件"],
  "expected_answer_keywords": ["完全民事行为能力", "意思表示", "不违反法律"]
}
```

两套预置数据集：`legal/legal_basic`、`finance/finance_basic`。

### 4.2 评测流程

`runner.py::EvalRunner`

```python
async def run(self, dataset_name, run_fn) -> list[CaseResult]:
    cases = load_dataset(dataset_name)
    for c in cases:
        answer, contexts, latency_ms = await run_fn(c.query)
        cr = CaseResult(
            case_id=c.id, answer=answer, latency_ms=latency_ms,
            correctness=correctness_score(answer, c.expected_answer_keywords or c.expected_keywords),
            groundedness=groundedness_score(answer, contexts),
            retrieval_recall=retrieval_recall(contexts, c.expected_keywords),
            context_precision=context_precision(contexts, c.expected_keywords),
        )
        if self.db: await self._persist(dataset_name, cr)
    return results
```

`run_fn` 是调用方注入的执行函数（`query -> (answer, retrieved_contexts, latency_ms)`），解耦评测器与 Runtime。

四个指标：

| 指标 | 计算 | 含义 |
|------|------|------|
| `correctness` | 答案命中 `expected_answer_keywords` 的比例 | 答案是否覆盖要点 |
| `groundedness` | 答案覆盖上下文 4-gram 的比例 | 答案是否基于检索内容（防幻觉） |
| `retrieval_recall` | 检索片段覆盖 `expected_keywords` 的比例 | 召回是否齐全 |
| `context_precision` | 含 query 关键词的检索片段占比 | 召回是否精准 |

> **诚实声明**：这些是**启发式指标**，非 LLM-as-judge。`correctness` 仅看关键词命中，`groundedness` 看 4-gram 覆盖——粗糙但可重复、零 LLM 成本。后续可加 LLM-as-judge 作为补充。

### 4.3 持久化

`EvalResult` 表：每次 case 的每个指标一行（`dataset_name, metric, score, payload`）。`/evals/results?dataset=...` 查回历史，对比版本间的回归。

### 4.4 Bad Case 闭环

`analyzer.py::BadCaseAnalyzer`

```python
def analyze(self, results) -> dict:
    bad = [r for r in results if r.correctness < self.threshold]   # 默认 0.5
    avg = {k: mean(v) for k, v in metric_scores.items()}
    weak = min(avg.items(), key=lambda x: x[1])[0]                  # 最低分指标
    return {"total": ..., "bad_case_count": ..., "bad_cases": [...],
            "averages": avg, "weak_metric": weak, "avg_latency_ms": ...}
```

输出：

- **bad_cases 列表**：哪些 case 挂了，定位到具体 case_id。
- **weak_metric**：全数据集平均分最低的指标——指明下一轮优化方向（召回弱就改检索，groundedness 弱就改 prompt 强约束基于上下文）。
- **avg_latency_ms**：性能基线。

闭环用法：跑 eval → analyzer 分析 → 找到 weak_metric + bad_cases → 针对性改 prompt / 分块 / 检索 → 重跑 eval 验证分数提升。

### 4.5 触发方式

- **API**：`POST /evals/run {"dataset": "legal/legal_basic"}`。
- **脚本**：`scripts/run_evals.py`（CI 友好）。
- **集成测试**：`tests/evals/` 下有用 stub LLM 的回归测试，保证指标计算逻辑本身不退化。

---

## 5. OpenTelemetry 迁移(已完成,Phase 7)

> 状态:已落地。迁移点收敛在 `tracer.py` / `metrics.py` 内部,调用方(`auth.py`、`chat.py`、`admin.py`、`audit_service.py`)零改动--这是抽象层的价值。

落地内容:

1. **Span 模型**:用 `opentelemetry.trace.Span` 替代自研 `Span`,`request_trace` / `span` 改调 `_tracer.start_as_current_span(name)`。OTel span context 的 `trace_id`/`span_id`(hex)回填到兼容层 `Span` dataclass,供 `auth.py::span.trace_id` 与测试断言消费。
2. **导出器**:`OTEL_EXPORTER_OTLP_ENDPOINT` 配置时用 `OTLPSpanExporter`(gRPC),否则 `ConsoleSpanExporter`。OTLP exporter 包缺失时回退 console。
3. **采样**:`ParentBased(TraceIdRatioBased(settings.OTEL_TRACES_SAMPLER_RATIO))`,默认 1.0 全量,生产建议 0.1。父 span 已采样则子 span 强制采样,保持链路完整。
4. **metrics 双写**:`metrics.inc` -> 进程内 `_counters[name] += v` + `_otel_counter(name).add(v)` 镜像;`metrics.observe` -> 进程内 `_timers[name]` + `_otel_histogram(name).record(ms)`。`snapshot()` 仍从进程内 dict 取,保持 `{counters, timers}` 结构,`/admin/metrics` 端点零改动。OTel 侧聚合导出由 reader/exporter 负责。
5. **保留审计表**:`AuditService` 不变,trace_id 仍写库,OTel 与审计表通过 trace_id 互查。
6. **Evals 升级**:新增 LLM-as-judge(`app/evals/metrics/llm_judge.py`),与启发式指标并行记录。`EVALS_LLM_JUDGE` 开关默认 false(省 LLM 成本),CI 跑启发式,定期手动开。

关键修复点:`_span_stack_var.reset(token)` 必须放在外层 `try/finally`,否则 yield 内抛异常时 contextvar 不复位,跨测试/跨请求泄漏 span 栈。

配置新增:`OTEL_TRACES_SAMPLER_RATIO: float = 1.0`、`EVALS_LLM_JUDGE: bool = False`。依赖新增 `opentelemetry-api/sdk/exporter-otlp >= 1.43.0`。
---

## 6. 可观测性全景

```
HTTP 请求
   │
   ▼
request_trace("chat")          ← 生成 trace_id
   │
   ├── audit.log(trace_id, "chat_request", ...)   ← 审计表
   │
   ├── runtime.run(state)
   │     ├── @trace IntentNode.execute
   │     ├── @trace PlannerNode.execute
   │     ├── @trace RetrievalNode.execute
   │     │     └── @trace rag.search
   │     ├── @trace ToolNode.execute
   │     │     └── @trace tool.execute
   │     ├── @trace AnswerNode.execute
   │     │     └── @trace llm.generate
   │     └── @trace ReflectionNode.execute
   │
   ├── audit.log(trace_id, "chat_response", ...)
   │
   ▼
span_end 日志（含 trace_id / span_id / parent_id / duration_ms）
   │
   ▼
日志聚合系统（ELK / Loki）按 trace_id 重建链路

旁路：
   metrics.inc / metrics.time  →  /admin/metrics snapshot
   EvalRunner.run              →  eval_results 表 + BadCaseAnalyzer
```

---

## 7. 当前限制

1. **未接 OTel**:见 §5,自研 tracing 不对接标准生态。**已解除**(Phase 7 迁移完成)。
2. **metrics 进程内**:多 worker 不聚合,无持久化。**部分解除**(Phase 7:镜像到 OTel Counter/Histogram,由 OTel reader/exporter 聚合导出;进程内 snapshot 仍保留供 `/admin/metrics` 本地查看)。
3. **eval 指标粗糙**:关键词命中 + 4-gram,非语义级评分。**部分解除**(Phase 7:新增 LLM-as-judge,与启发式并行记录,`EVALS_LLM_JUDGE` 开关按需启用)。
4. **无 bad case 自动回归**:analyzer 输出靠人看,未接入"发现 bad case -> 自动建 issue"的闭环。
5. **trace 采样**:当前全量记录 span_end 日志,高 QPS 下日志量爆炸。**已解除**(Phase 7:`ParentBased(TraceIdRatioBased(ratio))` 采样率可配,生产建议 0.1)。