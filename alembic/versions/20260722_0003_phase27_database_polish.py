"""phase 2.7 database polish

Revision ID: 20260722_0003
Revises: 20260722_0002
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "20260722_0003"
down_revision = "20260722_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """补齐 Phase 2.7 审查后确认的宽表和索引口径。"""

    op.add_column("orders_wide", sa.Column("user_role", sa.String(length=32), server_default="", nullable=False))
    op.add_column(
        "orders_wide",
        sa.Column("primary_product_price", sa.Numeric(12, 2), server_default="0.00", nullable=False),
    )
    op.add_column("orders_wide", sa.Column("item_count", sa.Integer(), server_default="1", nullable=False))
    op.add_column("orders_wide", sa.Column("refund_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "orders_wide",
        sa.Column("total_refund", sa.Numeric(12, 2), server_default="0.00", nullable=False),
    )
    op.add_column("orders_wide", sa.Column("has_refund", sa.Boolean(), server_default=sa.text("0"), nullable=False))
    op.add_column(
        "orders_wide",
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_valid_range", "coupons", ["valid_from", "valid_to"], unique=False)
    op.add_column("product_price_history", sa.Column("change_reason", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """回滚 Phase 2.7 polish 增量，保留 0002 的 14 表基础结构。"""

    op.drop_column("product_price_history", "change_reason")
    op.drop_index("ix_valid_range", table_name="coupons")

    op.drop_column("orders_wide", "updated_at")
    op.drop_column("orders_wide", "has_refund")
    op.drop_column("orders_wide", "total_refund")
    op.drop_column("orders_wide", "refund_count")
    op.drop_column("orders_wide", "item_count")
    op.drop_column("orders_wide", "primary_product_price")
    op.drop_column("orders_wide", "user_role")
