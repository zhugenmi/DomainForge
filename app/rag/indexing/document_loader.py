from __future__ import annotations

from pathlib import Path

from app.rag.parser import parse


def load_document(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    return parse(p)


def load_text(text: str) -> str:
    return text


__all__ = ["load_document", "load_text"]
