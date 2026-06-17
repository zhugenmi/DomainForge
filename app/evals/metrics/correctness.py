from __future__ import annotations


def keyword_hit_rate(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    hits = sum(1 for k in keywords if k and k in answer)
    return hits / len(keywords)


def correctness_score(answer: str, expected_keywords: list[str]) -> float:
    """基于关键词命中的正确性评分（0-1）。"""
    return keyword_hit_rate(answer, expected_keywords)


__all__ = ["correctness_score", "keyword_hit_rate"]
