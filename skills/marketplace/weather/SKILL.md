---
name: weather
description: "Use when the user asks about current weather, temperature, or forecast for a city. Triggers on questions like 'X天气怎么样'、'weather in X'、'X多少度'."
version: "1.0.0"
author: domainforge
license: MIT
---

# Weather

当用户询问某地天气时，**直接调用 `weather` 工具**，不要尝试用 shell 命令或 `web_search` 凑天气信息。

## 调用方式

调用 `weather` 工具，参数：
- `city`：城市名（中文或英文，如 `成都`、`London`）
- `units`：可选，`m` 公制（默认）/ `u` 美制

工具内部已用 httpx 直连 wttr.in，返回紧凑文本如 `成都: ⛅️ +8°C`。

## 行为约定

1. 用户未明示城市但有上下文时（如"今天天气怎么样"且对话已提及某地），用上下文城市；否则询问。
2. 拿到结果后用自然语言简述，不要原样吐工具返回串。
3. 若工具返回 `error`，告知用户查询失败并建议换城市名重试。
4. wttr.in 仅支持当前天气；用户问"未来三天"时，明确告知仅能提供当前状况。

## 示例

用户："成都今天天气怎么样"
→ 调用 `weather(city="成都")`，拿到 `成都: ⛅️ +8°C` 后回复：
"成都现在 ⛅️，气温 8°C。"
