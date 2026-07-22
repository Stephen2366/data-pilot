"""database upgrade to 14 physical tables

Revision ID: 20260722_0002
Revises: 20260717_0001
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa

revision = "20260722_0002"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 Phase 2.7 数据库升级：7 表扩展为 14 张物理表。"""

    # 类目树先创建，再让 products.category_id 指向它。
    op.create_table(
        "product_categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["product_categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_categories_level"), "product_categories", ["level"], unique=False)
    op.create_index(op.f("ix_product_categories_name"), "product_categories", ["name"], unique=False)
    op.create_index(op.f("ix_product_categories_parent_id"), "product_categories", ["parent_id"], unique=False)
    op.create_index(op.f("ix_product_categories_status"), "product_categories", ["status"], unique=False)

    op.add_column("products", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_products_category_id", "products", "product_categories", ["category_id"], ["id"])
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)

    # 订单头增强：兼容旧字段，同时新增源系统单号和金额口径字段。
    op.add_column("orders", sa.Column("source_order_no", sa.String(length=80), nullable=True))
    op.add_column("orders", sa.Column("external_order_no", sa.String(length=80), nullable=True))
    op.add_column(
        "orders",
        sa.Column("shipping_amount", sa.Numeric(12, 2), server_default="0.00", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0.00", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("actual_amount", sa.Numeric(12, 2), server_default="0.00", nullable=False),
    )
    op.alter_column("orders", "paid_at", existing_type=sa.DateTime(), nullable=True)
    op.create_index(op.f("ix_orders_external_order_no"), "orders", ["external_order_no"], unique=False)
    op.create_index(op.f("ix_orders_source_order_no"), "orders", ["source_order_no"], unique=False)

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("item_discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("item_actual_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=64), nullable=False),
        sa.Column("product_name_snapshot", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "line_no", name="uk_order_line"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index("ix_order_items_order_product", "order_items", ["order_id", "product_id"], unique=False)
    op.create_index(op.f("ix_order_items_product_id"), "order_items", ["product_id"], unique=False)
    op.create_index("ix_order_items_product", "order_items", ["product_id"], unique=False)

    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("coupon_code", sa.String(length=64), nullable=False),
        sa.Column("coupon_name", sa.String(length=120), nullable=False),
        sa.Column("coupon_type", sa.String(length=32), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("min_order_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coupon_code"),
    )
    op.create_index(op.f("ix_coupons_coupon_type"), "coupons", ["coupon_type"], unique=False)
    op.create_index(op.f("ix_coupons_status"), "coupons", ["status"], unique=False)

    op.create_table(
        "order_coupons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("coupon_id", sa.Integer(), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["coupon_id"], ["coupons.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "coupon_id", name="uk_order_coupon"),
    )
    op.create_index(op.f("ix_order_coupons_coupon_id"), "order_coupons", ["coupon_id"], unique=False)
    op.create_index("ix_order_coupons_coupon_order", "order_coupons", ["coupon_id", "order_id"], unique=False)
    op.create_index(op.f("ix_order_coupons_order_id"), "order_coupons", ["order_id"], unique=False)

    op.add_column("refunds", sa.Column("source_order_no", sa.String(length=80), nullable=True))
    op.add_column("refunds", sa.Column("order_item_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_refunds_order_item_id", "refunds", "order_items", ["order_item_id"], ["id"])
    op.create_index(op.f("ix_refunds_order_item_id"), "refunds", ["order_item_id"], unique=False)
    op.create_index(op.f("ix_refunds_source_order_no"), "refunds", ["source_order_no"], unique=False)

    op.create_table(
        "user_behavior_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("device_type", sa.String(length=48), nullable=False),
        sa.Column("page_url", sa.String(length=240), nullable=True),
        sa.Column("referrer", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("event_time", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_behavior_device_event", "user_behavior_log", ["device_type", "event_type"], unique=False)
    op.create_index("ix_behavior_event_time_type", "user_behavior_log", ["event_time", "event_type"], unique=False)
    op.create_index("ix_behavior_session_event", "user_behavior_log", ["session_id", "event_type"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_channel_id"), "user_behavior_log", ["channel_id"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_device_type"), "user_behavior_log", ["device_type"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_event_time"), "user_behavior_log", ["event_time"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_event_type"), "user_behavior_log", ["event_type"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_product_id"), "user_behavior_log", ["product_id"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_session_id"), "user_behavior_log", ["session_id"], unique=False)
    op.create_index(op.f("ix_user_behavior_log_user_id"), "user_behavior_log", ["user_id"], unique=False)

    op.create_table(
        "product_price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=False),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("price_source", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_price_history_is_current"), "product_price_history", ["is_current"], unique=False)
    op.create_index(op.f("ix_product_price_history_product_id"), "product_price_history", ["product_id"], unique=False)
    op.create_index("ix_price_history_current", "product_price_history", ["product_id", "is_current"], unique=False)
    op.create_index(
        "ix_price_history_product_window",
        "product_price_history",
        ["product_id", "valid_from", "valid_to"],
        unique=False,
    )

    op.create_table(
        "orders_wide",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("source_order_no", sa.String(length=80), nullable=True),
        sa.Column("external_order_no", sa.String(length=80), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_name", sa.String(length=80), nullable=False),
        sa.Column("user_status", sa.String(length=24), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("channel_code", sa.String(length=48), nullable=False),
        sa.Column("channel_name", sa.String(length=120), nullable=False),
        sa.Column("channel_type", sa.String(length=48), nullable=False),
        sa.Column("order_status", sa.String(length=32), nullable=False),
        sa.Column("order_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("shipping_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", name="uk_orders_wide_order_id"),
    )
    op.create_index("ix_orders_wide_batch", "orders_wide", ["batch_id"], unique=False)
    op.create_index("ix_orders_wide_category", "orders_wide", ["category"], unique=False)
    op.create_index(op.f("ix_orders_wide_category_id"), "orders_wide", ["category_id"], unique=False)
    op.create_index(op.f("ix_orders_wide_channel_id"), "orders_wide", ["channel_id"], unique=False)
    op.create_index(op.f("ix_orders_wide_order_no"), "orders_wide", ["order_no"], unique=False)
    op.create_index(op.f("ix_orders_wide_order_status"), "orders_wide", ["order_status"], unique=False)
    op.create_index(op.f("ix_orders_wide_paid_at"), "orders_wide", ["paid_at"], unique=False)
    op.create_index("ix_orders_wide_paid_channel", "orders_wide", ["paid_at", "channel_id"], unique=False)
    op.create_index(op.f("ix_orders_wide_product_id"), "orders_wide", ["product_id"], unique=False)
    op.create_index(op.f("ix_orders_wide_user_id"), "orders_wide", ["user_id"], unique=False)


def downgrade() -> None:
    """回滚 Phase 2.7 升级：先删新子表，再移除旧表新增列。"""

    # MySQL 会为外键列依赖索引；整表删除会自动清掉表内索引，比逐个 drop index 更稳。
    # 使用 IF EXISTS 是为了让非事务 DDL 的中断复跑仍可恢复。
    op.execute("DROP TABLE IF EXISTS orders_wide")
    op.execute("DROP TABLE IF EXISTS product_price_history")
    op.execute("DROP TABLE IF EXISTS user_behavior_log")

    op.drop_constraint("fk_refunds_order_item_id", "refunds", type_="foreignkey")
    op.drop_index(op.f("ix_refunds_source_order_no"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_item_id"), table_name="refunds")
    op.drop_column("refunds", "order_item_id")
    op.drop_column("refunds", "source_order_no")

    op.execute("DROP TABLE IF EXISTS order_coupons")
    op.execute("DROP TABLE IF EXISTS coupons")
    op.execute("DROP TABLE IF EXISTS order_items")

    op.drop_index(op.f("ix_orders_source_order_no"), table_name="orders")
    op.drop_index(op.f("ix_orders_external_order_no"), table_name="orders")
    # 新 schema 允许未支付订单 paid_at=NULL；旧 schema 回滚前需要给这些行一个兜底时间。
    op.execute("UPDATE orders SET paid_at = COALESCE(created_at, NOW()) WHERE paid_at IS NULL")
    op.alter_column("orders", "paid_at", existing_type=sa.DateTime(), nullable=False)
    op.drop_column("orders", "actual_amount")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "shipping_amount")
    op.drop_column("orders", "external_order_no")
    op.drop_column("orders", "source_order_no")

    op.drop_constraint("fk_products_category_id", "products", type_="foreignkey")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_column("products", "category_id")

    op.execute("DROP TABLE IF EXISTS product_categories")
