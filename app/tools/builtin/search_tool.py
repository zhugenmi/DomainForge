from __future__ import annotations

import html as _html
import re
from typing import Any

import httpx

from app.tools.base import Tool
from app.tools.registry.schema import ToolParameter, ToolSchema

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_B_ALGO_RE = re.compile(r'<li class="b_algo".*?</li>', re.DOTALL)
_TITLE_RE = re.compile(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>', re.DOTALL)
_URL_RE = re.compile(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"', re.DOTALL)
_SNIPPET_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _strip_html(s: str) -> str:
    s = _TAG_RE.sub("", s)
    s = _html.unescape(s)
    return _WS_RE.sub(" ", s).strip()


def _parse_bing(html: str, top_k: int) -> list[dict]:
    out: list[dict] = []
    for block in _B_ALGO_RE.findall(html):
        title_m = _TITLE_RE.search(block)
        url_m = _URL_RE.search(block)
        snippet_m = _SNIPPET_RE.search(block)
        if not title_m or not url_m:
            continue
        out.append(
            {
                "title": _strip_html(title_m.group(1)),
                "url": url_m.group(1),
                "snippet": _strip_html(snippet_m.group(1)) if snippet_m else "",
            }
        )
        if len(out) >= top_k:
            break
    return out


class SearchTool(Tool):
    name = "web_search"
    description = "通过 Bing 进行网络搜索，返回前 N 条结果（标题/链接/摘要）"
    schema = ToolSchema(parameters=[
        ToolParameter(name="query", type="string", description="搜索关键词"),
        ToolParameter(name="top_k", type="integer", description="返回条数", required=False, default=5),
    ])
    permission_scope = "default"
    timeout = 15.0

    BING_URL = "https://www.bing.com/search"

    async def execute(self, **kwargs: Any) -> list[dict]:
        query = kwargs["query"]
        top_k = int(kwargs.get("top_k", 5) or 5)
        params = {
            "q": query,
            "cc": "us",
            "setLang": "en",
            "count": str(top_k),
        }
        headers = {"User-Agent": _USER_AGENT}
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.BING_URL, params=params, headers=headers)
            resp.raise_for_status()
        return _parse_bing(resp.text, top_k)
