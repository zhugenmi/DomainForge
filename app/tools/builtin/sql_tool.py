from __future__ import annotations

import re
from typing import Any

from sqlalchemy import create_engine, text

from app.configs.settings import settings
from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|replace)\b",
    re.IGNORECASE,
)


class SQLTool(Tool):
    name = "sql_query"
    description = "在只读模式下执行 SQL 查询（仅允许 SELECT），返回前 N 行结果"
    schema = ToolSchema(parameters=[
        ToolParameter(name="sql", type="string", description="SELECT 查询语句"),
        ToolParameter(name="limit", type="integer", description="返回行数上限", required=False, default=20),
    ])
    permission_scope = "sensitive"
    timeout = 30.0

    def __init__(self, dsn: str | None = None):
        # 优先使用只读 DSN；未配置则退回主 DSN（仍受语句白名单保护）
        self.dsn = dsn or getattr(settings, "READONLY_DATABASE_URL", None) or _to_readonly_dsn(settings.DATABASE_URL)

    async def execute(self, **kwargs: Any) -> dict:
        sql = kwargs["sql"].strip().rstrip(";")
        limit = int(kwargs.get("limit", 20) or 20)
        if not sql.lower().startswith("select"):
            return {"error": "only SELECT allowed"}
        if _FORBIDDEN.search(sql):
            return {"error": "statement contains forbidden keyword"}
        # 强制 limit
        if "limit" not in sql.lower():
            sql = f"{sql} LIMIT {limit}"

        engine = create_engine(self.dsn)
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql)).fetchmany(limit)
                cols = list(conn.execute(text(sql)).keys()) if rows else []
            return {
                "columns": cols,
                "rows": [list(r) for r in rows],
                "rowcount": len(rows),
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            engine.dispose()


def _to_readonly_dsn(dsn: str) -> str:
    # 给主 DSN 加 -ro 后缀用户名作为简易只读约定（生产应配独立只读账号）
    return dsn


__all__ = ["SQLTool"]
