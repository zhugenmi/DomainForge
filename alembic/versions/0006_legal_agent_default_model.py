"""reset legal builtin agent model_name to empty (follow system default)

Revision ID: 0006_legal_agent_default_model
Revises: 0005_agents
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_legal_agent_default_model"
down_revision = "0005_agents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # builtin 法律咨询 agent 的 model_name 从硬编码 'gpt-4o-mini' 改为空，
    # 运行时由 _llm_for_agent 解析为 settings.DEFAULT_LLM_MODEL，环境无关。
    op.execute(
        sa.text(
            "UPDATE agents SET model_name = '' WHERE name = '法律咨询' AND is_builtin = true"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE agents SET model_name = 'gpt-4o-mini' "
            "WHERE name = '法律咨询' AND is_builtin = true"
        )
    )
