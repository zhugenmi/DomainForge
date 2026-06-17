from __future__ import annotations

import re
from pathlib import Path

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_RE = re.compile(r"<(script|style).*?</\1>", re.DOTALL | re.IGNORECASE)


def parse_html(text: str) -> str:
    text = _SCRIPT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def parse_file(path: Path) -> str:
    return parse_html(path.read_text(encoding="utf-8", errors="replace"))


__all__ = ["parse_html", "parse_file"]
