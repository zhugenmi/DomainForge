from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.observability.logging.logger import get_logger

logger = get_logger("mcp.client")


@dataclass
class MCPTool:
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


class MCPClient:
    """Model Context Protocol 客户端最小实现。

    通过 HTTP/JSON-RPC 与 MCP Server 通信：
    - list_tools: 获取 server 暴露的工具列表
    - call_tool: 调用具体工具
    若 server_url 未配置，方法返回空结果，保证调用方链路不阻塞。
    """

    def __init__(self, server_url: str | None = None, timeout: float = 30.0):
        self.server_url = server_url
        self.timeout = timeout
        self._id = 0

    def available(self) -> bool:
        return bool(self.server_url)

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def list_tools(self) -> list[MCPTool]:
        if not self.available():
            return []
        try:
            resp = await self._rpc("tools/list", {})
            return [
                MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                )
                for t in resp.get("tools", [])
            ]
        except Exception as e:
            logger.warning("mcp_list_tools_failed", error=str(e))
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self.available():
            return {"error": "MCP server not configured"}
        try:
            resp = await self._rpc("tools/call", {"name": name, "arguments": arguments})
            return resp.get("content", resp)
        except Exception as e:
            return {"error": str(e)}

    async def _rpc(self, method: str, params: dict) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self.server_url, json=payload)  # type: ignore[arg-type]
            r.raise_for_status()
            data = r.json()
        if "error" in data and data["error"]:
            raise RuntimeError(json.dumps(data["error"]))
        return data.get("result", {})


__all__ = ["MCPClient", "MCPTool"]
