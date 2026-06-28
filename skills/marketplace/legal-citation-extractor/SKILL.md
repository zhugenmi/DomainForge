---
name: legal-citation-extractor
description: "Use when extracting, formatting, or verifying legal citations from Chinese legal documents (法条引用、裁判文书). Triggers on citation extraction, statute reference formatting, or legal document analysis tasks."
version: "1.0.0"
author: domainforge
license: MIT
---

# Legal Citation Extractor

当用户需要从中文法律文书中提取、格式化或校验法条引用时，遵循以下指令。

## 提取规则

1. 识别形如「《XX法》第N条第M款」的引用结构。
2. 区分法律名称、条文序号、款项层级。
3. 对每条引用输出标准化格式：`《法律全称》第X条第Y款第Z项`。

## 输出格式

按引用在原文中出现顺序编号列出，附原文上下文片段（≤30字）。

## 校验

若引用的法律名称疑似不存在或条文序号超出常识范围，标注「⚠ 待核验」。
