"""eval_results, memory session/embedding, chunk tsv/score

Revision ID: 0002_eval_memory_tsv
Revises: 63a3219fddeb
Create Date: 2026-06-17 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_eval_memory_tsv"
down_revision: Union[str, None] = "63a3219fddeb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_name", sa.String(length=100), nullable=False),
        sa.Column("metric", sa.String(length=100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_results_dataset_name"), "eval_results", ["dataset_name"], unique=False)

    # memory: session_id + embedding + metadata
    op.add_column("memories", sa.Column("session_id", sa.Uuid(), nullable=True))
    op.add_column("memories", sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True))
    op.add_column("memories", sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index(op.f("ix_memories_user_id"), "memories", ["user_id"], unique=False)
    op.create_index(op.f("ix_memories_session_id"), "memories", ["session_id"], unique=False)
    op.create_index(op.f("ix_memories_memory_type"), "memories", ["memory_type"], unique=False)

    # chunk: tsv + score
    op.add_column("document_chunks", sa.Column("tsv", postgresql.TSVECTOR(), nullable=True))
    op.add_column("document_chunks", sa.Column("score", sa.Float(), nullable=True))
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_tsv ON document_chunks USING GIN (tsv)"
    )
    # backfill tsv from content (english config; chinese fallback in app layer)
    op.execute("UPDATE document_chunks SET tsv = to_tsvector('simple', content)")


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_tsv"), table_name="document_chunks")
    op.drop_column("document_chunks", "score")
    op.drop_column("document_chunks", "tsv")
    op.drop_index(op.f("ix_memories_memory_type"), table_name="memories")
    op.drop_index(op.f("ix_memories_session_id"), table_name="memories")
    op.drop_index(op.f("ix_memories_user_id"), table_name="memories")
    op.drop_column("memories", "metadata")
    op.drop_column("memories", "embedding")
    op.drop_column("memories", "session_id")
    op.drop_index(op.f("ix_eval_results_dataset_name"), table_name="eval_results")
    op.drop_table("eval_results")
