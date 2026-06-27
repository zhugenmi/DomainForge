from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.category_repo import CategoryRepo
from app.database.repositories.document_repo import DocumentRepo
from app.tools.base import Tool
from app.tools.registry.schema import ToolSchema


class ListKnowledgeBasesTool(Tool):
    """列出当前系统已配置的知识库（类别）目录，含文档数/字数/最近更新。

    用于回答"当前有哪些知识库"这类元问题，避免模型凭训练知识编造清单。
    """

    name = "list_knowledge_bases"
    description = "列出当前系统中已配置的所有知识库（类别）目录，包含文档数、字数、最近更新时间"
    schema = ToolSchema(parameters=[])
    permission_scope = "read"
    timeout = 5.0

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, **kwargs: Any) -> list[dict]:
        cat_repo = CategoryRepo(self.db)
        doc_repo = DocumentRepo(self.db)
        categories = await cat_repo.list_all()
        stats = await doc_repo.get_stats_by_domain()
        stats_map = {s["domain"]: s for s in stats}
        return [
            {
                "name": c.name,
                "is_builtin": c.is_builtin,
                "file_count": int(stats_map.get(c.name, {}).get("file_count", 0) or 0),
                "word_count": int(stats_map.get(c.name, {}).get("word_count", 0) or 0),
                "last_updated": stats_map.get(c.name, {}).get("last_updated"),
            }
            for c in categories
        ]
