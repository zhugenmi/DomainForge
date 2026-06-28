from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentUpload(BaseModel):
    domain: str
    title: str
    source: str = ""
    content: str


class IndexRequest(BaseModel):
    domain: str
    chunk_size: int = 500
    chunk_overlap: int = 50


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class ChunkResult(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    content: str
    metadata: dict = {}
    score: float | None = None


class SearchResponse(BaseModel):
    results: list[ChunkResult]


# ---- 知识库重构：类别 / 文档 / 两阶段导入 ----


class CategoryStats(BaseModel):
    name: str
    is_builtin: bool = False
    file_count: int = 0
    word_count: int = 0
    last_updated: datetime | None = None


class DocumentInfo(BaseModel):
    id: uuid.UUID
    domain: str
    title: str
    source: str = ""
    file_type: str | None = None
    file_size_bytes: int | None = None
    word_count: int | None = None
    chunk_count: int | None = None
    status: str = "indexed"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FilePreview(BaseModel):
    filename: str
    file_type: str
    file_size_bytes: int
    char_count: int
    word_count: int
    chunk_count: int
    sample_chunks: list[str] = Field(default_factory=list)


class PreviewSession(BaseModel):
    session_id: uuid.UUID
    domain: str
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    embedding_dimension: int
    expires_in: int
    files: list[FilePreview]


class ConfirmRequest(BaseModel):
    session_id: uuid.UUID


class ConfirmResponse(BaseModel):
    """confirm 立即返回：导入已排队，前端轮询 status。"""
    job_id: uuid.UUID
    status: str = "pending"


class ImportJobStatus(BaseModel):
    job_id: uuid.UUID
    status: str  # pending | running | succeeded | failed
    total_files: int = 0
    processed_files: int = 0
    total_chunks: int = 0
    processed_chunks: int = 0
    document_ids: list[uuid.UUID] = Field(default_factory=list)
    error: str | None = None


class CategoryCreate(BaseModel):
    name: str


class CategoryInfo(BaseModel):
    id: uuid.UUID
    name: str
    is_builtin: bool
