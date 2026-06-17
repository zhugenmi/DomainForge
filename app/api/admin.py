from __future__ import annotations

from fastapi import APIRouter, Depends

from app.observability.metrics.metrics import metrics
from app.security.permission import require_role
from app.tools.builtin.calculator_tool import CalculatorTool
from app.tools.builtin.file_tool import FileReadTool, FileWriteTool
from app.tools.builtin.knowledge_tool import KnowledgeTool
from app.tools.builtin.search_tool import SearchTool
from app.tools.builtin.sql_tool import SQLTool
from app.tools.registry.registry import ToolRegistry

router = APIRouter(prefix="/admin", tags=["admin"])


def _build_full_registry() -> ToolRegistry:
    reg = ToolRegistry()
    # KnowledgeTool 仅读取类级元数据（name/schema/description），rag_service 传 None 即可
    for tool in [CalculatorTool(), SearchTool(), SQLTool(), KnowledgeTool(rag_service=None), FileReadTool(), FileWriteTool()]:
        reg.register(tool)
    return reg


@router.get("/tools")
async def list_tools():
    """列出所有已知内置工具的 schema（不依赖运行时注册）。"""
    reg = _build_full_registry()
    return [
        {
            "name": t.name,
            "description": t.description,
            "permission_scope": t.permission_scope,
            "timeout": t.timeout,
            "parameters": [p.model_dump() for p in t.schema.parameters],
        }
        for t in reg.list_tools()
    ]


@router.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


@router.get("/health/detail")
async def health_detail(user=Depends(require_role("admin"))):
    return {
        "status": "ok",
        "metrics": metrics.snapshot(),
        "user": user,
    }
