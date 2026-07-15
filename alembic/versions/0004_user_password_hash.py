"""user password_hash column for prod login

Revision ID: 0004_user_password_hash
Revises: 0003_knowledge_redesign
Create Date: 2026-06-27 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_password_hash"
down_revision: Union[str, None] = "0003_knowledge_redesign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
