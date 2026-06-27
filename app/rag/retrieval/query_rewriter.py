from __future__ import annotations

import json
import re

from app.llm.base import LLMProvider
from app.observability.logging.logger import get_logger

logger = get_logger("rag.query_rewriter")

_REWRITE_PROMPT = """你是查询改写器。把用户查询改写为多个用于检索的子查询，用于提升混合召回。

规则：
- 指代消解：把"它/这个/该"等指代替换为具体实体。
- 子查询分解：多问查询拆成独立子查询。
- 术语扩展：补同义词或近义表述。
- 保留原查询作为第一条。

只输出 JSON 数组，每项是一个字符串。不要输出其他内容。

对话历史（可能为空）：
{history}

用户查询：{query}
"""

# 启发式：短查询且无指代词，跳过改写避免无谓 LLM 调用
_REFERENCE_WORDS = ("它", "这个", "该", "那个", "其", "此", "上面", "前面")
_MIN_LEN_FOR_REWRITE = 12
_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _should_rewrite(query: str) -> bool:
    if len(query) < _MIN_LEN_FOR_REWRITE:
        return False
    return any(w in query for w in _REFERENCE_WORDS) or any(
        c in query for c in ("和", "与", "及", "，", "、", "并且", "以及")
    )


class QueryRewriter:
    """基于 LLM 的查询改写：指代消解 + 子查询分解 + 术语扩展。"""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def rewrite(self, query: str, history: list[dict] | None = None) -> list[str]:
        """返回改写后的子查询列表（含原 query）。简单查询直接返回 [query]。"""
        if not _should_rewrite(query):
            return [query]
        history_text = "\n".join(
            f"{m.get('role', 'user')}: {m.get('content', '')}" for m in (history or [])
        )[:500]
        prompt = _REWRITE_PROMPT.format(history=history_text or "(空)", query=query)
        try:
            raw = await self.llm.generate(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=200,
            )
            rewrites = _parse_rewrites(raw)
        except Exception as e:
            logger.warning("query_rewrite_failed", error=str(e), fallback="original")
            return [query]
        if not rewrites:
            return [query]
        # 保证原 query 在首位
        if rewrites[0] != query:
            rewrites = [query] + rewrites
        return rewrites


def _parse_rewrites(raw: str) -> list[str]:
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except json.JSONDecodeError:
        pass
    m = _JSON_ARRAY_RE.search(raw)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return [str(x) for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return []


__all__ = ["QueryRewriter", "_should_rewrite"]
