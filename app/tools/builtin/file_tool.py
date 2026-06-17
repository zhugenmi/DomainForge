from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema

SANDBOX_ROOT = Path(os.getenv("FILE_TOOL_ROOT", "./data/uploads")).resolve()


class FileReadTool(Tool):
    name = "file_read"
    description = "读取沙箱目录内的文件内容"
    schema = ToolSchema(parameters=[
        ToolParameter(name="path", type="string", description="相对于沙箱根的文件路径"),
    ])
    permission_scope = "read"
    timeout = 10.0

    async def execute(self, **kwargs: Any) -> dict:
        path = _safe_path(kwargs["path"])
        if not path.exists() or not path.is_file():
            return {"error": f"file not found: {path}"}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": str(e)}
        return {"path": str(path), "size": len(content), "content": content[:8000]}


class FileWriteTool(Tool):
    name = "file_write"
    description = "向沙箱目录写入文件（覆盖）"
    schema = ToolSchema(parameters=[
        ToolParameter(name="path", type="string", description="相对路径"),
        ToolParameter(name="content", type="string", description="文件内容"),
    ])
    permission_scope = "sensitive"
    timeout = 10.0

    async def execute(self, **kwargs: Any) -> dict:
        path = _safe_path(kwargs["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(kwargs["content"], encoding="utf-8")
        return {"path": str(path), "size": len(kwargs["content"])}


def _safe_path(rel: str) -> Path:
    root = SANDBOX_ROOT
    root.mkdir(parents=True, exist_ok=True)
    target = (root / rel).resolve()
    if root not in target.parents and target != root:
        raise PermissionError(f"path escapes sandbox: {rel}")
    return target


__all__ = ["FileReadTool", "FileWriteTool", "SANDBOX_ROOT"]
