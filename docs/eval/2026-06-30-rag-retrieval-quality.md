# RAG 子系统检索质量评测

> 评测日期:2026-06-30
> 评测脚本:`scripts/run_rag_eval.py`
> 受控语料:`data/raw_documents/{legal,finance}/`,带 gold 数据集 `app/evals/datasets/{legal,finance}/*_rag.json`
> 设计原则:直调 `HybridRetriever`,绕开 Agent(工具调用/路由),隔离 RAG 子系统本身;不调对话 LLM,只调 embedding + rerank,单轮可复现

---

## 1. 评测方法

### 1.1 受控语料

6 篇手写 markdown(legal 3 / finance 3),每篇含一个唯一 gold 子串段落答对应 query,其余段落带重叠干扰词(如"代理权""股价"在多个 chunk 出现),用以检验检索能否把对的段落排到前面。

### 1.2 Ground truth 用子串而非 chunk id

gold 子串在全文唯一,命中即正确召回,不依赖导入时生成的 chunk id,语料重新导入结果仍可复现。

### 1.3 两臂 A/B(同查询同 RRF 短路,唯一差异是最终重排)

- `rrf_only`:注入 `IdentityRerank`(按 RRF 原顺序返回)= 双路召回 + RRF 融合的基线
- `rrf_rerank`:真实 `QwenReranker`(qwen3-rerank)= 生产完整管线

### 1.4 指标(二值相关性,gold 命中即 relevant)

| 指标 | 定义 |
|---|---|
| Recall@k | top-k 中命中 gold 子串的比例 |
| MRR@10 | 首个命中 gold 的倒数排名 |
| NDCG@5 | gold 位置加权(DCG 用 1/log2(rank+1),IDCG=1) |
| Context Precision@5 | top-5 中含 gold 的 chunk 占比 |

### 1.5 Tier 3 引用定位完整率

对 `rrf_rerank` 的 top-5 调 `make_citations`,统计 locator 非空率(≠"相关段落")与 legal chapter 非空率,验证引用定位链。

---

## 2. 聚合结果(6 cases,legal×3 + finance×3)

| 指标 | RRF-only | RRF+Rerank | Δ(lift) |
|---|---:|---:|---:|
| Recall@5 | 1.000 | 1.000 | 0.000 |
| Recall@10 | 1.000 | 1.000 | 0.000 |
| MRR@10 | 0.917 | 0.917 | 0.000 |
| NDCG@5 | 0.938 | 0.938 | 0.000 |
| Context Precision@5 | 0.200 | 0.200 | 0.000 |

**Tier 3 引用定位完整率**:locator 非空率 15/30 = 0.500;legal chapter 非空率 15/15 = 1.000。

---

## 3. 业务量化结论

### 3.1 双路召回 + RRF 的基础检索质量已达标

在受控语料上 Recall@5=1.0、MRR@10=0.917、NDCG@5=0.938,6 个 query 的 gold 段落全部进入 top-5,其中 5 个直接排到第 1。即"对的段落基本都能捞到且排得很靠前"。

### 3.2 Rerank 在本语料上净 lift 为零,但 per-case 有双向作用

rerank 在 `finance-rag-001` 把 gold 从 rank2 拉到 rank1(MRR 0.5->1.0,qwen3-rerank 对"货币基金"定义句给出更高相关性),但在 `legal-rag-001` 把 gold 从 rank1 推到 rank2(MRR 1.0->0.5,"合同订立条件"query 与第十四条正文词面重叠高,rerank 反而降权了正确条文)。两 case 正好抵消。

**结论**:当 RRF 已将 gold 排到第 1 时,rerank 不带来额外收益,个别情况下反而引入噪声;rerank 的价值体现在 RRF 排序靠后的硬 case 上。受控语料规模小(6 query)且过于干净,未触发 rerank 的真正价值场景,需更大噪声语料验证。

### 3.3 Context Precision@5=0.2 暴露信噪比问题

top-5 中平均仅 1 条含 gold(5 条里 4 条是干扰段落),即检索把对的捞到了,但也夹带了 4 条无关 chunk。生产上这会稀释 LLM 上下文、增加 token 成本。

**根因**:受控语料每域仅 3 篇、干扰段落词面与 query 重叠,召回阶段无判别力--这是小语料固有问题,真实语料下应观察该指标是否回升。

### 3.4 引用定位链完整

legal chapter 非空率 100%(章节追踪修复有效,见 [fix/2026-06-27-citation-chapter-missing.md](../fix/2026-06-27-citation-chapter-missing.md));但 locator 整体非空率仅 50%--finance 域 chunk 无 `article` 元数据且正文无"第X条",locator 退路全为"相关段落"。**finance 分块策略未产出可定位的 locator**,是引用体验的已知缺口。

---

## 4. 复现

```bash
docker-compose up -d postgres && alembic upgrade head
python scripts/build_index.py --dir data/raw_documents/legal   --domain legal   --strategy legal
python scripts/build_index.py --dir data/raw_documents/finance --domain finance --strategy finance
python scripts/run_rag_eval.py
```

前置 `.env` 配置:`LLM_API_KEY` / `LLM_BASE_URL` / `EMBEDDING_*` / `RERANK_*`(同 [architecture/03_enhanced_rag.md](../architecture/03_enhanced_rag.md) §配置)。
