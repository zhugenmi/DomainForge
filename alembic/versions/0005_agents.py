"""create agents table and seed legal builtin agent

Revision ID: 0005_agents
Revises: 0004_user_password_hash
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_agents"
down_revision = "0004_user_password_hash"
branch_labels = None
depends_on = None

LEGAL_SYSTEM_PROMPT = """你是一名专业的法律咨询助手。请严格依据检索到的法律知识（法条、案例、条款）回答用户问题。

回答要求：
1. 优先引用检索到的知识库内容；若知识库无相关内容，明确告知并提示用户补充信息，不得编造法条或案例。
2. 涉及具体法律建议时，提示用户咨询专业律师，不替代正式法律意见。
3. 回答结构清晰，必要时分点说明。
"""


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("domain", sa.String(50), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "agent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO agents (id, name, description, system_prompt, model_name, temperature, domain, is_builtin) "
            "VALUES (gen_random_uuid(), '法律咨询', :desc, :prompt, '', 0.3, 'legal', true)"
        ).bindparams(desc="基于法律知识库的智能法律咨询助手", prompt=LEGAL_SYSTEM_PROMPT)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM agents WHERE name = '法律咨询' AND is_builtin = true"))
    op.drop_column("sessions", "agent_id")
    op.drop_table("agents")
