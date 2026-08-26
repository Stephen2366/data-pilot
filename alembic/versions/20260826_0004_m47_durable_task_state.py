"""M47 durable task checkpoint and typed event ledger.

Revision ID: 20260826_0004
Revises: 20260722_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20260826_0004"
down_revision = "20260722_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建两张独立 Agent 状态表，不触碰 14 张业务表。"""

    op.create_table(
        "agent_task_checkpoints",
        sa.Column("task_key", sa.String(64), primary_key=True),
        sa.Column("task_safe_ref", sa.String(80), nullable=False),
        sa.Column("owner_ref", sa.String(64), nullable=False),
        sa.Column("tenant_ref", sa.String(64), nullable=False),
        sa.Column("active_role", sa.String(64), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("state_version", sa.String(64), nullable=False),
        sa.Column("state_identity", sa.String(64), nullable=True),
        sa.Column("state_payload", sa.JSON(), nullable=True),
        sa.Column("claim_token_hash", sa.String(64), nullable=True),
        sa.Column("expires_at_us", sa.BigInteger(), nullable=False),
        sa.Column("purge_after_us", sa.BigInteger(), nullable=True),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
        sa.Column("updated_at_us", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_agent_task_checkpoint_expiry", "agent_task_checkpoints", ["status", "expires_at_us"])
    op.create_index("ix_agent_task_checkpoint_purge", "agent_task_checkpoints", ["purge_after_us"])
    op.create_table(
        "agent_task_events",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_schema_version", sa.String(64), nullable=False),
        sa.Column("event_identity", sa.String(64), nullable=False, unique=True),
        sa.Column("task_key", sa.String(64), nullable=False),
        sa.Column("task_safe_ref", sa.String(80), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("version_before", sa.BigInteger(), nullable=True),
        sa.Column("version_after", sa.BigInteger(), nullable=True),
        sa.Column("state_identity", sa.String(64), nullable=True),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("created_at_us", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_agent_task_event_task_version", "agent_task_events", ["task_key", "version_after"])


def downgrade() -> None:
    """仅回滚 M47 自有表。"""

    op.drop_index("ix_agent_task_event_task_version", table_name="agent_task_events")
    op.drop_table("agent_task_events")
    op.drop_index("ix_agent_task_checkpoint_purge", table_name="agent_task_checkpoints")
    op.drop_index("ix_agent_task_checkpoint_expiry", table_name="agent_task_checkpoints")
    op.drop_table("agent_task_checkpoints")
