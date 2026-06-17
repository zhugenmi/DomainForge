import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _vector_type():
    try:
        from pgvector.sqlalchemy import Vector
        from app.configs.settings import settings
        # sqlite 下用 JSON 存储向量（仅供测试），PG 上使用 pgvector
        return Vector(settings.EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite")
    except Exception:
        return JSON


def _tsvector_type():
    from sqlalchemy import Text

    try:
        from sqlalchemy.dialects.postgresql import TSVECTOR
        return TSVECTOR().with_variant(Text(), "sqlite")
    except Exception:
        return Text


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(_vector_type(), nullable=True)
    tsv = mapped_column(_tsvector_type(), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
