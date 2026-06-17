from __future__ import annotations

import re
from dataclasses import dataclass

_SENT_SPLIT = re.compile(r"(?<=[。！？!?\.])\s+")


@dataclass
class Chunk:
    text: str
    metadata: dict


def chunk_semantic(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    metadata: dict | None = None,
) -> list[Chunk]:
    """按段落 + 句子边界的语义分块；超出 chunk_size 时按字符重叠切。"""
    if not text:
        return []
    base_meta = metadata or {}
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    buf = ""
    idx = 0
    for para in paragraphs:
        if len(buf) + len(para) <= chunk_size:
            buf = f"{buf}\n{para}".strip() if buf else para
            continue
        if buf:
            chunks.append(Chunk(buf, {**base_meta, "chunk_index": idx}))
            idx += 1
            # overlap: 保留末尾
            buf = buf[-overlap:] if overlap > 0 else ""
        # 段落本身过长则按句切
        if len(para) > chunk_size:
            sentences = _SENT_SPLIT.split(para)
            for s in sentences:
                if len(buf) + len(s) <= chunk_size:
                    buf = f"{buf}{s}".strip() if buf else s
                else:
                    if buf:
                        chunks.append(Chunk(buf, {**base_meta, "chunk_index": idx}))
                        idx += 1
                        buf = s[-overlap:] if overlap > 0 else ""
                    else:
                        # 单句超过 chunk_size，硬切
                        for i in range(0, len(s), chunk_size - overlap):
                            chunks.append(Chunk(s[i : i + chunk_size], {**base_meta, "chunk_index": idx}))
                            idx += 1
                        buf = ""
        else:
            buf = para
    if buf:
        chunks.append(Chunk(buf, {**base_meta, "chunk_index": idx}))
    return chunks


__all__ = ["chunk_semantic", "Chunk", "split_by_pattern"]


def split_by_pattern(
    text: str,
    pattern: re.Pattern,
    meta_key: str,
    metadata: dict | None = None,
) -> list[Chunk]:
    """按正则锚点切分文本；无匹配时退化为段落切分。

    供 legal/finance 等领域分块器复用：每个匹配位置开始、到下一匹配之前
    结束为一块，把匹配文本写入 metadata[meta_key]。
    """
    if not text:
        return []
    base = metadata or {}
    matches = list(pattern.finditer(text))
    if not matches:
        return [
            Chunk(p.strip(), {**base, "chunk_index": i})
            for i, p in enumerate(text.split("\n\n"))
            if p.strip()
        ]
    chunks: list[Chunk] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            chunks.append(
                Chunk(block, {**base, "chunk_index": i, meta_key: m.group(0).strip()})
            )
    return chunks
