# DomainForge 运行时性能基线

> 评测日期:2026-07-01
> 评测脚本:`scripts/run_perf_eval.py`
> 指标:检索延迟 p50/p99、端到端响应时间 p50/p99、单次对话 Token 成本

---

## 1. 评测目标与范围

| 指标 | 定义 |
|---|---|
| 检索延迟 p50/p99 | `HybridRetriever.search()` 单次调用耗时(vector + bm25 + RRF + Rerank 全链路) |
| 端到端响应时间 p50/p99 | `AgentRuntime.run()` 单次完整对话耗时(intent -> planner -> retrieval -> answer -> reflection 全节点) |
| Token 成本 | 单次对话累计 LLM prompt/completion token + embedding token |

**不在范围**:并发吞吐压测(留待后续)、检索质量 Recall/MRR(见 [eval/2026-06-30-rag-retrieval-quality.md](2026-06-30-rag-retrieval-quality.md))、前端渲染耗时。

---

## 2. 评测方法

### 2.1 度量定义

- **延迟采集**:`time.perf_counter()` 包裹目标调用,单位 ms
- **p50/p99**:线性插值百分位 `percentile(xs, p)`,`k=(n-1)*p/100`,避免 `statistics.quantiles` 在小样本下的边界问题
- **Token 采集**:monkeypatch `openai.resources.chat.completions.AsyncCompletions.create` 与 `openai.resources.embeddings.AsyncEmbeddings.create`,从底层 `response.usage` 提取 `prompt_tokens`/`completion_tokens`/`total_tokens`。**不修改生产代码**,patch 仅在评测脚本上下文生效

### 2.2 采样规模

| 指标 | 样本数 | 构成 |
|---|---:|---|
| 检索延迟 | 60 | 6 cases(legal×3 + finance×3)× 10 次/case |
| 端到端响应时间 | 20 | 5 query × 4 次/query |
| Token 成本 | 20 | 随端到端采样同步采集,按对话切分 |

**p99 样本限制**:n=20 时 p99 ≈ max(第 99 百分位落在最大值附近),仅作粗略上界参考;n=60 的检索 p99 更可靠。

### 2.3 评测集

- 检索:复用 `app/evals/datasets/{legal,finance}/*_rag.json`
- 端到端:复用 `scripts/benchmark.py:SAMPLE_QUERIES`(5 条混合 query:寒暄 / 法律概念 / 计算 / 民法典 / 货币基金)

### 2.4 Token 采集实现

```
patch_openai_usage(counter) - contextmanager
  ├─ wrap AsyncCompletions.create -> 捕获 usage.prompt_tokens / completion_tokens
  └─ wrap AsyncEmbeddings.create  -> 捕获 usage.total_tokens
```

- 覆盖 `OpenAIProvider.generate` / `chat_with_tools` / `embed` 三条路径(均走底层 `AsyncOpenAI`)
- streaming 路径返回 `AsyncStream` 无 `.usage`,`getattr(resp, "usage", None)` 守卫跳过;`runtime.run()` 非流式,不触发 stream

---

## 3. 评测环境

| 项 | 值 |
|---|---|
| 对话 LLM | `deepseek-v4-pro`(DashScope 兼容模式) |
| Embedding | `text-embedding-v3`(dim=1024) |
| Rerank | `qwen3-rerank`(DashScope 原生扁平端点) |
| 数据库 | PostgreSQL(pgvector),Docker 容器 |
| 语料规模 | 5 文档 / 484 chunks(legal 4 + finance 1) |
| 机器 | Intel i7-14650HX(20 核),x86_64,WSL2 |

---

## 4. 量化结果

### 4.1 检索延迟(n=60)

| 统计量 | 值 (ms) |
|---|---:|
| p50 | **592.5** |
| p99 | **717.4** |
| mean | 581.4 |
| max | 729.9 |
| min | 449.5 |

### 4.2 端到端响应时间(n=20)

| 统计量 | 值 (ms) |
|---|---:|
| p50 | **10,465.1** |
| p99 | **25,175.9** |
| mean | 12,079.9 |
| max | 25,510.2 |
| min | 3,034.4 |

### 4.3 Token 成本(n=20 对话)

| 类别 | 均值 | 中位数 | 总和 |
|---|---:|---:|---:|
| LLM prompt | 47,347 | 47,384 | 946,933 |
| LLM completion | 4,268 | 4,090 | 85,355 |
| Embedding | 101 | 110 | 2,014 |
| **单对话合计** | **51,715** | **51,584** | - |

---

## 5. 分析与结论

### 5.1 检索延迟

p50 ≈ 592 ms、p99 ≈ 717 ms,分布紧凑(max/min 比 1.6×)。一次完整检索(双路召回 + RRF + DashScope rerank 网络往返)在百毫秒级完成,对用户感知不构成瓶颈。Rerank 的网络往返是主要耗时来源,离线退路 `rerank_simple` 会更快但质量下降。

### 5.2 端到端响应时间

p50 ≈ 10.5 s、p99 ≈ 25.2 s,**比检索延迟高一个数量级**,且分布右偏(mean 12 s > p50 10.5 s,max 25.5 s)。根因:Agent 单次对话触发多轮 LLM 调用(intent 识别 -> planner -> query 改写 -> answer 生成 -> reflection 评估,部分对话还有 tool_node 的 function-calling 轮次),每轮 LLM 调用 1-3 s,累加后达 10 s 级。

p99 与 p50 比值 2.4×,长尾主要来自:
1. 触发 tool 调用的 query(如计算题)多一轮 LLM + 工具执行
2. reflection 判定需重跑 answer 的情况
3. LLM API 自身尾延迟

**优化方向**:合并 intent + planner 为单次调用、reflection 仅在低置信度时触发、answer 流式返回首 token。

### 5.3 Token 成本

单对话均值 51,715 token,其中 **prompt 占 91.6%**(47,347 / 51,715),completion 占 8.3%,embedding 占 0.2%。prompt 占比高是因为:

- 每轮 LLM 调用都携带完整 system prompt + 工具描述 + 检索上下文(top-5 chunk,每 chunk ~500 字)
- 单对话平均 ~8 轮 LLM 调用,每轮 prompt ~6k token -> 累计 ~47k
- RAG 上下文在 answer 节点注入,单次就贡献 ~2-3k token

**成本优化方向**:
1. system prompt 缓存(DashScope/Anthropic 均支持 prompt caching,可削减重复 system 部分计费)
2. 压缩检索上下文(top-5 -> top-3,或 chunk 摘要)
3. 减少 LLM 轮次(见 5.2)

Embedding token 极低(均值 101)是因为 query embed 单条短文本;文档导入时的批量 embed 不计入对话成本。

---

## 6. 复现步骤

```bash
# 1. 启动 PG + 建索引
docker-compose up -d postgres && alembic upgrade head

# 2. 导入受控语料(同 eval/2026-06-30-rag-retrieval-quality.md §4)
python scripts/build_index.py --dir data/raw_documents/legal   --domain legal   --strategy legal
python scripts/build_index.py --dir data/raw_documents/finance --domain finance --strategy finance

# 3. 运行性能评测
python scripts/run_perf_eval.py
```

前置 `.env` 配置同 RAG 评测。

---

## 7. 已知限制

1. **p99 样本不足**:端到端 n=20 时 p99 ≈ max,仅作上界参考;检索 n=60 的 p99 更稳定。需 n≥100 才能得到稳定 p99,但端到端真实 LLM 调用成本制约了样本规模。
2. **真实 API 抖动**:评测依赖 DashScope 在线服务,网络与服务端负载会引入抖动。复跑可能得到 ±20% 偏差。评测期间曾观测到单次 e2e 触发 API 限流(429),需间隔重试。
3. **未压测并发**:本评测为串行单对话,未测量并发吞吐。`scripts/benchmark.py` 提供并发骨架,但本次未跑。
4. **语料规模小**:5 文档 / 484 chunks,检索延迟在小语料下偏乐观;真实生产语料(千文档级)下 BM25 与 vector 查询耗时可能上升,rerank 候选数也会变化。
5. **Token 仅计在线调用**:未计入文档导入时的历史 embed 成本(一次性,分摊到全生命周期更合理)。
6. **stream 路径未采集**:`runtime.run()` 非流式,token 完整捕获;若用 `run_stream()`,streaming 响应默认不带 usage,需 `stream_options={"include_usage": True}` 才能采集。
