# 全局 ToolRegistry 重复注册

> 日期:2026-06-17
> 类型:并发/状态污染
> 影响范围:`app/api/chat.py::_build_runtime` 每次请求构造 runtime 时

## 1. 问题现象

`ToolRegistry` 是模块级单例,每次请求调用 `_build_runtime()` 时会尝试注册工具。重复注册导致:
- registry 内同名工具被覆盖(行为可能不一致)
- 日志噪声(每次请求都走一遍注册逻辑)
- 潜在的并发写竞争(多请求同时注册)

## 2. 根因分析

### 直接原因

`registry.register(tool)` 无幂等检查,直接 `self._tools[name] = tool`。

### 根本原因

registry 是进程级单例,但 `_build_runtime` 是每请求调用。注册逻辑放在请求路径上本身是设计错误--工具应在应用启动时注册一次,而非每请求重复注册。Phase 1 为求简把注册放进了请求路径,留下此坑。

## 3. 解决方案

注册前先检查 `registry.get(name) is None`,避免重复注册:

```python
def _register_tool(registry, tool):
    if registry.get(tool.name) is None:
        registry.register(tool)
```

`_build_runtime` 调用此包装函数。

## 4. 验证

- `tests/tools/test_registry.py` 新增 `test_register_idempotent`:重复注册同名工具不覆盖、不报错。
- 多次请求后 `registry.list_tools()` 数量稳定。

## 5. 复盘

- **触发条件**:模块级单例 registry + 每请求注册路径。
- **预防**:启动时注册一次(lifespan 或模块 import 时),请求路径只读 registry。Phase 8 的 MCP 适配器注册即走 lifespan 模式(`_register_mcp_tools` 在启动时调一次)。
- **教训**:单例 + 请求路径写入是常见反模式,注册应幂等或挪出请求路径。
