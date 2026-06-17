from __future__ import annotations

import re
from typing import Any

import httpx

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


class SearchTool(Tool):
    name = "web_search"
    description = "通过 DuckDuckGo HTML 接口进行网络搜索，返回前 N 条结果摘要"
    schema = ToolSchema(parameters=[
        ToolParameter(name="query", type="string", description="搜索关键词"),
        ToolParameter(name="top_k", type="integer", description="返回条数", required=False, default=5),
    ])
    permission_scope = "default"
    timeout = 15.0

    DDG_URL = "https://html.duckduckgo.com/html/"

    async def execute(self, **kwargs: Any) -> list[dict]:
        query = kwargs["query"]
        top_k = int(kwargs.get("top_k", 5) or 5)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.DDG_URL, data={"q": query})
            resp.raise_for_status()
        text = _strip_html(resp.text)
        # 简单按句切分作为摘要返回
        snippets = [s.strip() for s in text.split(". ") if len(s.strip()) > 30]
        return [{"snippet": s[:300]} for s in snippets[:top_k]]
