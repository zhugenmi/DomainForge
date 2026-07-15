# 法律文档引用缺章节定位

> 日期:2026-06-27
> 类型:引用体验缺陷
> 影响范围:`app/rag/chunk/legal_chunker.py`、`app/rag/context/citation.py`、前端引用渲染

## 1. 问题现象

法律文档引用只显示 `民法典 · 第三十六条`,缺章节定位。用户无法从引用判断条文所属章节(如"第三章 劳动合同和集体合同"),降低了法律问答的可信度与可溯源性。

## 2. 根因分析

### 直接原因

`legal_chunker.py` 按"第X条"正则切分,但**不追踪条文所属章节**。chunk metadata 只含 `{article, chunk_index}`,无 `chapter` 字段。

### 根本原因

`Citation` 数据结构本身无 `chapter` 字段,`render_footnote` 也只渲染 `title · locator` 两行。要从"条"定位到"章",需要分块器在切条时向前扫描章节标题并写入 metadata--这是分块策略的职责缺失,不是渲染层问题。

## 3. 解决方案

### 3.1 legal_chunker 重写,向前追踪章节

`app/rag/chunk/legal_chunker.py`:
- 条文正则:`第[一二三四五六七八九十百千零〇0-9]+条`
- 章节正则:行首锚定 `第X章` + 章名(如 `第三章　劳动合同和集体合同`)
- 对每个条文匹配位置,**向前找最近的章节匹配**作为该条所属章名,写入 `metadata.chapter`
- 无"第X条"时退化为段落切分

```python
for match in article_re.finditer(text):
    start = match.start()
    # 向前扫描章节
    chapter = _find_preceding_chapter(text[:start])
    chunks.append(Chunk(content=..., metadata={..., "article": match.group(), "chapter": chapter}))
```

这样引用时能定位到"文件 -> 章 -> 条"。

### 3.2 Citation 加 chapter 字段

`app/rag/context/citation.py`:

```python
@dataclass
class Citation:
    index: int
    title: str
    chapter: str = ""   # 新增:"第三章　劳动合同和集体合同"(legal 专属)
    locator: str = ""
    snippet: str = ""
    document_id: str
    chunk_id: str
```

`make_citations` 填充 chapter(从 `metadata.chapter` 读);`render_footnote` 多行显示:

```
引用:
[1] 中华人民共和国劳动法_20181229.docx
    第三章　劳动合同和集体合同
    第三十六条　国家实行劳动者每日工作时间不超过八小时...
```

### 3.3 前端渲染同步

`CitationOut` schema 加 `chapter` 字段;前端 `Citation` 类型与 `ChatWorkspace.tsx` 渲染逻辑同步--有 chapter 时三行(标题 / 章节 / 摘要),无 chapter 时两行(标题 · locator / 摘要)。

## 4. 验证

- `tests/rag/test_legal_chunker.py`:断言 chunk metadata 含 chapter,且 chapter 与条文位置对应。
- `tests/rag/test_citation.py`:`make_citations` 填充 chapter,`render_footnote` 多行格式。
- 端到端:法律问答引用显示 `民法典 · 第三章 · 第三十六条`。

## 5. 复盘

- **注意**:已导入的旧法律文档无 chapter 元数据,需重新导入才生效。这是 metadata schema 变更的固有代价--旧 chunk 不会自动补全。
- **预防**:分块器产出的 metadata 应包含完整的定位层级(章/节/条/款),而非只切当前粒度。定位链越完整,引用体验越好。
- **复用**:`finance_chunker` 的 `heading` 字段同理应保留标题层级,供 Citation 定位。后续若加医疗分块器,按"主诉/现病史/诊断"切分时也应写入对应定位元数据。
