from __future__ import annotations

import json
import re

from app.llm.base import LLMProvider
from app.observability.logging.logger import get_logger
from app.runtime.planner.prompt import REFLECTION_PROMPT

logger = get_logger("reflection.evaluator")

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


async def evaluate_answer(
    llm: LLMProvider, query: str, answer: str, has_context: bool
) -> dict:
    """返回 {sufficient, reason, next_action}。失败时默认 sufficient=True 避免死循环。"""
    if not answer:
        return {"sufficient": False, "reason": "empty answer", "next_action": "answer"}
    prompt = REFLECTION_PROMPT.format(query=query, answer=answer, has_context=has_context)
    try:
        raw = await llm.generate(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=160,
        )
    except Exception as e:
        logger.warning("reflection_llm_failed", error=str(e))
        return {"sufficient": True, "reason": "reflection skipped", "next_action": "none"}

    raw = raw.strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = _JSON_OBJ_RE.search(raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"sufficient": True, "reason": "reflection unparsed, assume ok", "next_action": "none"}


__all__ = ["evaluate_answer"]
