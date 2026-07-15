"""knowledge redesign: categories table + document metadata columns

Revision ID: 0003_knowledge_redesign
Revises: 0002_eval_memory_tsv
Create Date: 2026-06-17 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_knowledge_redesign"
down_revision: Union[str, None] = "0002_eval_memory_tsv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # seed built-in categories
    op.execute(
        "INSERT INTO categories (id, name, is_builtin) VALUES "
        "(gen_random_uuid(), 'legal', true), "
        "(gen_random_uuid(), 'finance', true), "
        "(gen_random_uuid(), 'medical', true), "
        "(gen_random_uuid(), 'insurance', true), "
        "(gen_random_uuid(), 'enterprise', true)"
    )

    # documents: new metadata columns
    op.add_column("documents", sa.Column("file_type", sa.String(length=20), nullable=True))
    op.add_column("documents", sa.Column("file_size_bytes", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("word_count", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("chunk_count", sa.Integer(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="indexed"),
    )
    op.add_column(
        "documents",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_documents_domain"), "documents", ["domain"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_domain"), table_name="documents")
    op.drop_column("documents", "updated_at")
    op.drop_column("documents", "status")
    op.drop_column("documents", "chunk_count")
    op.drop_column("documents", "word_count")
    op.drop_column("documents", "file_size_bytes")
    op.drop_column("documents", "file_type")
    op.drop_table("categories")
