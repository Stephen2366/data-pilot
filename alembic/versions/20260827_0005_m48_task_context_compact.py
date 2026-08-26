"""M48 task context window and compact payload.

Revision ID: 20260827_0005
Revises: 20260826_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20260827_0005"
down_revision = "20260826_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只给 checkpoint 增加 bounded context 列；event v2 复用既有 JSON 表。"""

    op.add_column("agent_task_checkpoints", sa.Column("context_schema_version", sa.String(64), nullable=True))
    op.add_column("agent_task_checkpoints", sa.Column("context_identity", sa.String(64), nullable=True))
    op.add_column("agent_task_checkpoints", sa.Column("context_payload", sa.JSON(), nullable=True))
    op.add_column("agent_task_checkpoints", sa.Column("context_source_watermark", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """按创建逆序删除 M48 自有列，不触碰 M47 state/event。"""

    op.drop_column("agent_task_checkpoints", "context_source_watermark")
    op.drop_column("agent_task_checkpoints", "context_payload")
    op.drop_column("agent_task_checkpoints", "context_identity")
    op.drop_column("agent_task_checkpoints", "context_schema_version")
