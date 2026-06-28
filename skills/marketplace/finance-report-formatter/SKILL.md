---
name: finance-report-formatter
description: "Use when formatting financial reports (财报) into a standard structure. Triggers on financial statement restructuring, balance sheet/income statement formatting, or annual report summarization tasks."
version: "0.9.0"
author: domainforge
license: MIT
---

# Finance Report Formatter

当用户需要将财报内容整理为标准结构时，遵循以下指令。

## 标准结构

1. **资产负债表**：资产/负债/所有者权益三段式。
2. **利润表**：收入/成本/利润分层。
3. **现金流量表**：经营/投资/筹资三类。

## 数字规范

- 金额统一以「万元」为单位，千分位逗号分隔。
- 负数用括号表示，如 `(1,234)`。
- 同比/环比变化标注百分比，保留一位小数。

## 校验

资产总计 ≠ 负债 + 所有者权益时，标注「⚠ 不平」。
