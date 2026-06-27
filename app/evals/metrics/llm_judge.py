from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from app.observability.logging.logger import get_logger

if TYPE_CHECKING:
    from app.llm.base import LLMProvider

logger = get_logger("evals.llm_judge")

_RUBRIC = {
    "correctness": "答案是否在事实上与上下文/常识一致，无臆造、无错误法律/金融结论。",
    "groundedness": "答案是否仅基于给定上下文，未引入上下文外信息。",
    "helpfulness": "答案是否直接回应了 query，结构清晰、可执行。",
}


def _build_prompt(query: str, answer: str, contexts: list[str], rubric: str) -> str:
    ctx_block = "\n---\n".join(contexts) if contexts else "(无上下文)"
    return (
        "你是评估员。按 rubric 给答案打 0-1 分（保留两位小数），并给出一句评语。\n"
        "严格按 JSON 输出：{\"score\": float, \"comment\": str}\n\n"
        f"【Query】{query}\n\n"
        f"【上下文】\n{ctx_block}\n\n"
        f"【答案】{answer}\n\n"
        f"【Rubric】{rubric}\n"
    )


def _parse_score(raw: str) -> tuple[float, str]:
    """从 LLM 输出抽取 score 与 comment，容错处理 fence/前缀文本。"""
    if not raw:
        return 0.0, ""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    payload = fenced.group(1) if fenced else raw
    m = re.search(r"\{[^{}]*\}", payload, re.S)
    if not m:
        return 0.0, ""
    try:
        obj = json.loads(m.group(0))
        score = float(obj.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        return score, str(obj.get("comment", ""))
    except (ValueError, json.JSONDecodeError):
        return 0.0, ""


async def score(
    judge_llm: "LLMProvider",
    query: str,
    answer: str,
    contexts: list[str],
    rubric: str = "correctness",
) -> tuple[float, str]:
    """调 LLM 输出 0-1 分 + 评语。rubric ∈ correctness/groundedness/helpfulness。"""
    rubric_text = _RUBRIC.get(rubric, rubric)
    prompt = _build_prompt(query, answer, contexts, rubric_text)
    try:
        raw = await judge_llm.generate(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as e:
        logger.warning("llm_judge_failed", rubric=rubric, error=str(e))
        return 0.0, ""
    return _parse_score(raw)


__all__ = ["score"]
