from __future__ import annotations

import json
import re

from app.observability.logging.logger import get_logger

logger = get_logger("planner.decomposer")

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_plan(raw: str) -> list[dict]:
    """容错地从 LLM 输出中解析 JSON 计划数组。"""
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
            return data
    except json.JSONDecodeError:
        pass
    m = _JSON_ARRAY_RE.search(raw)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logger.warning("plan_parse_failed", raw=raw[:120])
    return []


def needs_planning(query: str) -> bool:
    """启发式：包含对比 / 多步 / 计算 / 检索关键词的查询需要规划。"""
    if len(query) < 12:
        return False
    keywords = ["对比", "比较", "计算", "首先", "然后", "步骤", "分析", "总结", "归纳", "between", "compare"]
    return any(k in query.lower() for k in keywords)


__all__ = ["parse_plan", "needs_planning"]
