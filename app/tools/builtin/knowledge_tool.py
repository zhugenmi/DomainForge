from __future__ import annotations

from typing import Any

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema


class KnowledgeTool(Tool):
    name = "knowledge_search"
    description = "搜索知识库文档，返回与查询相关的文档片段"
    schema = ToolSchema(parameters=[
        ToolParameter(name="query", type="string", description="搜索查询文本"),
        ToolParameter(name="top_k", type="integer", description="返回结果数量", required=False, default=5),
    ])
    permission_scope = "read"
    timeout = 10.0

    def __init__(self, rag_service: Any):
        self.rag_service = rag_service

    async def execute(self, **kwargs: Any) -> list[dict]:
        query = kwargs["query"]
        top_k = kwargs.get("top_k", 5)
        results = await self.rag_service.search(query, top_k=top_k)
        return [
            {
                "content": r.content,
                "document_id": str(r.document_id),
                "metadata": r.metadata_,
                "score": r.score,
            }
            for r in results
        ]
