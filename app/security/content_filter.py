from __future__ import annotations

import re
from dataclasses import dataclass

# 默认黑名单关键词（可按领域扩展）。仅做最小示意。
_DEFAULT_BLOCKLIST = [
    " bomb ",
    " explosives recipe",
    " child abuse",
    " 怎么制造炸弹",
]


@dataclass
class FilterResult:
    blocked: bool
    reason: str = ""


def check_content(text: str, extra: list[str] | None = None) -> FilterResult:
    if not text:
        return FilterResult(blocked=False)
    patterns = list(_DEFAULT_BLOCKLIST) + (extra or [])
    lowered = text.lower()
    for p in patterns:
        if p.lower() in lowered:
            return FilterResult(blocked=True, reason=f"blacklist_match: {p.strip()!r}")
    return FilterResult(blocked=False)


def mask_pii(text: str) -> str:
    """脱敏常见 PII：邮箱、手机号、身份证号。"""
    if not text:
        return text
    text = re.sub(r"\b1[3-9]\d{9}\b", "[PHONE]", text)
    text = re.sub(r"\b\d{15}(?:\d{2}[\dXx])?\b", "[IDCARD]", text)
    text = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", "[EMAIL]", text)
    return text


__all__ = ["check_content", "mask_pii", "FilterResult"]
