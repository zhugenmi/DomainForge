# RAG 引用编号乱序与 locator 无意义

> 日期:2026-06-28
> 类型:引用体验缺陷(非崩溃)
> 影响范围:`app/rag/context/citation.py`、`app/runtime/nodes/answer_node.py`、前端引用渲染

## 1. 问题现象

第一轮引用增强上线后,用户用宪法文本测试发现三个问题:

1. **引用编号乱序**:LLM 先标 `[4]`(国旗条款)再标 `[1][2]`,参考列表序号与正文不对应。
2. **参考列表序号重复**:`<ol>` 默认 `1.` decimal + span `[1]`,显示成 `1. [1]`。
3. **"第N段"无意义**:semantic 分块没条目号,locator 显示"第34段"对用户无定位价值。

## 2. 根因分析

### 2.1 LLM 不可靠地正序标注

LLM 按思考顺序标编号--先想到国旗就先标 `[4]`,再回头标 `[1][2]`。prompt 指示"按检索片段顺序标注"无效,LLM 行为不可控。

### 2.2 CSS 双重序号

`<ol>` 默认 `list-style: decimal` 显示 `1. 2. 3.`,同时 CitationList 组件又在每条加了 `[N]` span,导致 `1. [1]` `2. [2]` 重复。

### 2.3 locator 兜底用 chunk_index

`_locator(metadata, content)` 原优先级:
1. `metadata.article`(legal 分块的"第三条")
2. "第N段"(N = `metadata.chunk_index`)

semantic 分块无 `article`,全走"第N段"兜底。但 `chunk_index` 是内部切分序号,对用户无定位价值--"第34段"不能帮用户找到原文位置。

## 3. 解决方案

### 3.1 后端后处理重编号

新增 `reorder_citations(answer, citations) -> tuple[str, list[dict]]`:扫描 answer 里 `[N]` 的首次出现顺序,重编号为正序 1,2,3...;未被正文引用的过滤掉。

```python
def reorder_citations(answer: str, citations: list[dict]) -> tuple[str, list[dict]]:
    cite_indices = {c["index"] for c in citations}
    seen_order = []
    for m in _BRACKET_RE.finditer(answer):
        n = int(m.group(1))
        if n in cite_indices and n not in seen_order:
            seen_order.append(n)
    old_to_new = {old: new for new, old in enumerate(seen_order, start=1)}
    # 重写 answer 中所有 [N],重排 citations
    ...
```

LLM 乱标 `[4][1][2]` -> 规整为 `[1][2][3]`。`AnswerNode` 在 emit 前调用。

**设计权衡**:`reorder` 只重编号 citations 里存在的 index,未知编号(如 `[9]` 但无对应 chunk)原样保留不进列表。

### 3.2 CSS 去重

```css
ol.citations { list-style: none; padding-left: 0; }
```

去掉默认 decimal 序号,只保留 `[N]` span。

### 3.3 locator 智能提取

`_locator(metadata, content)` 改进优先级链:

1. `metadata.article`(legal 分块的"第三条")
2. 从 content 提取首个"第X条"(`_ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9]+条")`)--宪法修正案 semantic 分块内容含"第五十条",提取为 locator
3. "相关段落"(兜底)

不再显示无意义的"第N段"。

## 4. 验证

- `tests/rag/test_citation.py::test_reorder_citations_*`:乱序重编 / 过滤未引用 / 重复编号 / 未知编号 / 空输入。
- 端到端:宪法问答回答含 `[1][2][3]` 正序上标,底部参考文献列表序号不重复,locator 显示条目号(如"第一百四十一条")。

## 5. 复盘

- **设计原则:LLM 不生成参考列表**。参考文献列表由后端结构化下发,不让 LLM 生成。原因:LLM 会幻觉编号、格式漂移、漏项。LLM 只负责正文 `[N]` 标注,列表从 `state.citations`(真实检索 chunk)渲染,保证准确。
- **设计原则:后端后处理重编号 vs 让 LLM 直接正序**。LLM 不可靠,后端 `reorder_citations` 按出现顺序重编号是确定性的,保证正文与列表一致。代价是 answer 字符串需要二次处理(正则替换),但成本低。
- **行为变化**:`reorder_citations` 会过滤未被正文引用的 citation。如果 LLM 答案完全没标 `[N]`,参考列表不再显示(避免列出一堆未引用的 chunk)。这是有意为之--参考列表应与正文引用一一对应。
- **预防**:locator 兜底不能用内部序号(chunk_index),必须用对用户有意义的定位(条号/章节/标题)。"相关段落"比"第34段"诚实--前者承认无精确定位,后者假装有定位但无意义。
