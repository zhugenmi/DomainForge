from __future__ import annotations

from typing import Any

from app.observability.logging.logger import get_logger
from app.tools.base import Tool
from app.tools.mcp.client import MCPClient, MCPTool
from app.tools.registry.schema import ToolParameter, ToolSchema

logger = get_logger("mcp.adapter")


def _mcp_schema_to_tool_schema(input_schema: dict) -> ToolSchema:
    """MCP inputSchema（JSON Schema 形态）转 ToolSchema。

    MCP 工具的 inputSchema 通常是 {"type": "object", "properties": {...}, "required": [...]}。
    """
    props = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    required = set(input_schema.get("required", [])) if isinstance(input_schema, dict) else set()
    params: list[ToolParameter] = []
    for name, spec in props.items():
        params.append(
            ToolParameter(
                name=name,
                type=spec.get("type", "string") if isinstance(spec, dict) else "string",
                description=spec.get("description", "") if isinstance(spec, dict) else "",
                required=name in required,
            )
        )
    return ToolSchema(parameters=params)


class MCPToolAdapter(Tool):
    """将 MCP Server 远端工具适配为 Tool ABC，对 Runtime 透明。

    name/description/schema 从 MCPTool 元数据映射；execute 调 MCPClient.call_tool。
    permission_scope 默认 "default"——MCP 工具的敏感度由远端 server 决定，
    本地不臆测；如需对特定远端工具加确认，可由调用方 register 后覆写属性。
    """

    def __init__(self, client: MCPClient, mcp_tool: MCPTool):
        self._client = client
        self._mcp_tool = mcp_tool
        self.name = mcp_tool.name
        self.description = mcp_tool.description or f"MCP tool: {mcp_tool.name}"
        self.schema = _mcp_schema_to_tool_schema(mcp_tool.input_schema)
        self.permission_scope = "default"
        self.timeout = client.timeout

    async def execute(self, **kwargs: Any) -> Any:
        return await self._client.call_tool(self.name, kwargs)


async def register_mcp_tools(registry, client: MCPClient) -> int:
    """从 MCPClient.list_tools() 拉取远端工具，逐个注册到 registry。

    返回注册数量。client 不可用或 list_tools 失败时返回 0，不抛异常。
    """
    if not client.available():
        return 0
    try:
        tools = await client.list_tools()
    except Exception as e:
        logger.warning("mcp_register_list_failed", error=str(e))
        return 0
    count = 0
    for t in tools:
        if not t.name:
            continue
        adapter = MCPToolAdapter(client, t)
        registry.register(adapter)
        count += 1
    if count:
        logger.info("mcp_tools_registered", count=count)
    return count


__all__ = ["MCPToolAdapter", "register_mcp_tools"]
