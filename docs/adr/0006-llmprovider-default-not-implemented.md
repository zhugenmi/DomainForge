# ADR 0006:chat_with_tools 用非抽象方法默认抛 NotImplementedError

> 状态:已采纳 | 日期:2026-06-27

## 背景

Phase 4 把 function-calling 抽象到 `LLMProvider` 接口,新增 `chat_with_tools(messages, tools, tool_choice) -> ToolCallResponse`。需决定该方法是 `@abstractmethod` 还是普通方法。

## 决策

`chat_with_tools` 是**非抽象方法**,默认实现抛 `NotImplementedError`:

```python
class LLMProvider(ABC):
    ...
    async def chat_with_tools(self, messages, tools, tool_choice="auto", **kwargs) -> ToolCallResponse:
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")
```

支持的 provider(如 `OpenAIProvider`)覆写;不支持的保留默认,调用方拿到清晰错误。

## 理由

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| `@abstractmethod` 强制所有子类实现 | 5 个 Provider 子类 + 测试中的 `StubProvider`/`StubLLM` 必须全部实现,否则无法实例化;Stub 只需 `generate`/`stream`/`embed`,会被强制加空实现,破坏大量测试 |

### 选"非抽象默认抛错"的理由

1. **"不支持工具"是可表达的语义**:默认抛 `NotImplementedError` 让"该 provider 不支持 function-calling"成为一等语义。`FallbackPolicy` 捕获 `NotImplementedError` 后跳过该 provider 换下一个,而非视为故障。
2. **旧 stub 零改动**:测试中的 Stub 不实现 `chat_with_tools`,保留默认抛错;若测试调到该方法,抛错即"该 stub 不支持工具"的清晰信号,而非实例化失败。
3. **新 provider 按需实现**:支持工具的 provider 覆写,不支持的不写--与"能力可选"的语义一致。
4. **与 Python ABC 习惯一致**:`abc.ABC` 允许非抽象方法,默认抛错是 stdlib 常见模式(如 `io.IOBase.write` 对只读流默认抛 `UnsupportedOperation`)。

## 后果

- **正面**:旧测试零改动;新 provider 按需实现;能力缺失可表达。
- **负面**:`chat_with_tools` 不在 ABC 强制契约内,IDE 不报"未实现"警告--但 `NotImplementedError` 运行时即报,风险可控。
- **FallbackPolicy 协同**:`chat_with_tools` 逐 provider 尝试,`except NotImplementedError: continue`(能力缺失,静默跳过),`except Exception: record failure + switch`(调用失败,记后切)。两类异常分开处理是关键--前者不是故障。
- **复用**:后续若新增"能力可选"的接口方法(如 `stream_with_tools`、`embed_with_rerank`),同此模式:非抽象 + 默认抛 NotImplementedError + 调用方捕获后降级。
