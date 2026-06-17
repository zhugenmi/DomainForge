from __future__ import annotations


def groundedness_score(answer: str, contexts: list[str]) -> float:
    """简单 groundedness：答案中出现的"上下文片段"占比。

    将每个 context 切成 4-gram，统计被答案覆盖的比例。
    """
    if not answer or not contexts:
        return 0.0
    answer_lower = answer.lower()
    total = 0
    hit = 0
    for ctx in contexts:
        grams = _ngrams(ctx, 4)
        if not grams:
            continue
        total += len(grams)
        for g in grams:
            if g in answer_lower:
                hit += 1
    return hit / total if total else 0.0


def _ngrams(text: str, n: int) -> list[str]:
    chars = [c for c in text if c.strip()]
    if len(chars) < n:
        return ["".join(chars)] if chars else []
    return ["".join(chars[i : i + n]) for i in range(len(chars) - n + 1)]


__all__ = ["groundedness_score"]
