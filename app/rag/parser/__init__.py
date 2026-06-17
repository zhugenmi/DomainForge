from __future__ import annotations

from pathlib import Path

from app.rag.parser.docx_parser import parse_docx
from app.rag.parser.html_parser import parse_html
from app.rag.parser.markdown_parser import parse_markdown
from app.rag.parser.pdf_parser import parse_pdf
from app.rag.parser.xlsx_parser import parse_xlsx


def parse(path: Path) -> str:
    """根据扩展名自动选择解析器（路径版）。"""
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
    if suffix in {".html", ".htm"}:
        return parse_html(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".pdf":
        return parse_pdf(path=path)
    if suffix == ".docx":
        return parse_docx(path=path)
    if suffix in {".xlsx", ".xls"}:
        return parse_xlsx(path=str(path))
    return path.read_text(encoding="utf-8", errors="replace")


def parse_bytes(filename: str, data: bytes) -> str:
    """根据文件名扩展名解析字节内容（HTTP 上传场景）。"""
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return parse_markdown(data.decode("utf-8", errors="replace"))
    if suffix in {".html", ".htm"}:
        return parse_html(data.decode("utf-8", errors="replace"))
    if suffix == ".pdf":
        return parse_pdf(data=data)
    if suffix == ".docx":
        return parse_docx(data=data)
    if suffix in {".xlsx", ".xls"}:
        return parse_xlsx(data=data)
    return data.decode("utf-8", errors="replace")


def detect_file_type(filename: str) -> str:
    """返回标准化的文件类型标签（用于 Document.file_type 列）。"""
    suffix = Path(filename).suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "md"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix in {".xlsx", ".xls"}:
        return "xlsx"
    if suffix in {".txt", ".text"}:
        return "txt"
    return "other"


__all__ = [
    "parse",
    "parse_bytes",
    "parse_markdown",
    "parse_html",
    "parse_pdf",
    "parse_docx",
    "parse_xlsx",
    "detect_file_type",
]
