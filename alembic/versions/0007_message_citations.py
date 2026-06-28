"""add citations JSON column to messages

Revision ID: 0007_message_citations
Revises: 0006_legal_agent_default_model
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_message_citations"
down_revision: Union[str, None] = "0006_legal_agent_default_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("citations", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "citations")
