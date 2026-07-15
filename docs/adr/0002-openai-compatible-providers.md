# ADR 0002:所有 LLM Provider 走 OpenAI 兼容协议

> 状态:已采纳 | 日期:2026-06-17

## 背景

需支持多家 LLM(OpenAI、DeepSeek、GLM、Qwen、Gemini)。各家有原生 SDK 也有 OpenAI 兼容端点。

## 决策

所有 Provider 继承 `OpenAIProvider`,仅覆盖 `base_url` / `model` 默认值,**不引入厂商专属 SDK**。

## 理由

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| 每家厂商用原生 SDK(google-genai、dashscope 等) | 5 个 SDK 依赖体积大;API 风格各异,`LLMProvider` 抽象层要写 5 套适配;版本升级风险 5 倍 |
| 只支持 OpenAI | 国内场景 DeepSeek/GLM/Qwen 是主流,不能只支持 OpenAI |

### 选 OpenAI 兼容的理由

1. **国内主流厂商均提供 OpenAI 兼容 API**:DeepSeek、GLM(智谱)、Qwen(DashScope)、火山方舟都兼容 `/v1/chat/completions` 协议,改 `base_url` 即可。
2. **薄子类设计**:5 个 Provider 子类各 ~10 行,只设默认 base_url + model。统一走 `AsyncOpenAI` 客户端,不引入厂商 SDK。
3. **function-calling 协议统一**:OpenAI 的 `tools` / `tool_calls` 格式被广泛模仿,5 家都兼容,`ToolNode` 一套逻辑通吃。
4. **测试简化**:stub 一个 `OpenAIProvider` 子类即可,不需为每家厂商 mock SDK。

## 后果

- **正面**:依赖体积小;新增 provider 只需 ~10 行子类;function-calling 协议统一。
- **负面**:非 OpenAI 兼容协议(如原生 Gemini API、Anthropic Messages API)无法直接接入,需重写 provider。
- **已知 gap**:`ToolNode` 原先直连 `llm.client`(OpenAI SDK 私有属性),Phase 4 已抽象为 `LLMProvider.chat_with_tools`(见 [adr/0006-llmprovider-default-not-implemented.md](0006-llmprovider-default-not-implemented.md))。
- **迁移成本**:若未来必须接原生 Gemini/Anthropic,需为该 provider 单独重写 `chat_with_tools` + `generate`,其他 provider 不受影响。
