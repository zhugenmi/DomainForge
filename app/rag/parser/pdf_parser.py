from __future__ import annotations

from pathlib import Path


def parse_pdf(data: bytes | None = None, path: Path | None = None) -> str:
    """从 PDF 抽取文本。依赖 pypdf；失败时返回空串避免阻塞。"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    if path is not None:
        reader = PdfReader(str(path))
    elif data is not None:
        from io import BytesIO

        reader = PdfReader(BytesIO(data))
    else:
        return ""
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(p for p in parts if p).strip()


def parse_file(path: Path) -> str:
    return parse_pdf(path=path)


__all__ = ["parse_pdf", "parse_file"]
