from __future__ import annotations


def retrieval_recall(retrieved: list[str], expected_keywords: list[str]) -> float:
    """召回率：检索片段中覆盖期望关键词的比例。"""
    if not expected_keywords:
        return 1.0
    joined = " ".join(retrieved)
    hits = sum(1 for k in expected_keywords if k and k in joined)
    return hits / len(expected_keywords)


def context_precision(retrieved: list[str], query_keywords: list[str]) -> float:
    """精确率：检索片段中包含查询关键词的片段占比。"""
    if not retrieved:
        return 0.0
    relevant = sum(1 for r in retrieved if any(k in r for k in query_keywords))
    return relevant / len(retrieved)


__all__ = ["retrieval_recall", "context_precision"]
