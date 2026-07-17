"""create m1 business tables

Revision ID: 20260717_0001
Revises:
Create Date: 2026-07-17
"""

from alembic import op
import sqlalchemy as sa


revision = "20260717_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 用户维表 ================================================================
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_name", sa.String(length=80), nullable=False, comment="用户展示名"),
        sa.Column(
            "role",
            sa.String(length=32),
            nullable=False,
            comment="RBAC 角色：admin / ops / customer_service / demo_user",
        ),
        sa.Column("email", sa.String(length=160), nullable=False, comment="敏感字段：邮箱"),
        sa.Column("phone", sa.String(length=32), nullable=False, comment="敏感字段：手机号"),
        sa.Column("status", sa.String(length=24), nullable=False, comment="用户状态"),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)
    op.create_index(op.f("ix_users_status"), "users", ["status"], unique=False)

    # 商品、渠道维表 ==========================================================
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("product_name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("launched_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index(op.f("ix_products_category"), "products", ["category"], unique=False)
    op.create_index(
        op.f("ix_products_product_name"), "products", ["product_name"], unique=False
    )
    op.create_index(op.f("ix_products_status"), "products", ["status"], unique=False)

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("channel_code", sa.String(length=48), nullable=False),
        sa.Column("channel_name", sa.String(length=120), nullable=False),
        sa.Column(
            "channel_type",
            sa.String(length=48),
            nullable=False,
            comment="渠道类型，如 paid / organic / partner",
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_code"),
    )
    op.create_index(
        op.f("ix_channels_channel_type"), "channels", ["channel_type"], unique=False
    )
    op.create_index(op.f("ix_channels_status"), "channels", ["status"], unique=False)

    # 订单事实表 ==============================================================
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column(
            "order_status",
            sa.String(length=32),
            nullable=False,
            comment="订单状态：paid / shipped / delivered / cancelled",
        ),
        sa.Column("order_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
    )
    op.create_index(op.f("ix_orders_channel_id"), "orders", ["channel_id"], unique=False)
    op.create_index(
        "ix_orders_paid_at_channel", "orders", ["paid_at", "channel_id"], unique=False
    )
    op.create_index(op.f("ix_orders_paid_at"), "orders", ["paid_at"], unique=False)
    op.create_index(
        "ix_orders_product_paid_at", "orders", ["product_id", "paid_at"], unique=False
    )
    op.create_index(op.f("ix_orders_product_id"), "orders", ["product_id"], unique=False)
    op.create_index(
        op.f("ix_orders_order_status"), "orders", ["order_status"], unique=False
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)

    # 退款事实表 ==============================================================
    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("refund_no", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column(
            "refund_status",
            sa.String(length=32),
            nullable=False,
            comment="退款状态：requested / approved / rejected / completed",
        ),
        sa.Column(
            "refund_reason",
            sa.String(length=64),
            nullable=False,
            comment="退款原因，例如 quality_issue",
        ),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refund_no"),
    )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"], unique=False)
    op.create_index(op.f("ix_refunds_product_id"), "refunds", ["product_id"], unique=False)
    op.create_index(
        "ix_refunds_reason_status", "refunds", ["refund_reason", "refund_status"], unique=False
    )
    op.create_index(
        op.f("ix_refunds_refund_reason"), "refunds", ["refund_reason"], unique=False
    )
    op.create_index(
        op.f("ix_refunds_refund_status"), "refunds", ["refund_status"], unique=False
    )
    op.create_index(
        op.f("ix_refunds_requested_at"), "refunds", ["requested_at"], unique=False
    )
    op.create_index(op.f("ix_refunds_user_id"), "refunds", ["user_id"], unique=False)

    # 工单与知识库 ============================================================
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_no", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("ticket_type", sa.String(length=64), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=24),
            nullable=False,
            comment="优先级：low / medium / high / urgent",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            comment="工单状态：pending / processing / resolved / closed",
        ),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_no"),
    )
    op.create_index(
        op.f("ix_tickets_assigned_user_id"), "tickets", ["assigned_user_id"], unique=False
    )
    op.create_index(op.f("ix_tickets_order_id"), "tickets", ["order_id"], unique=False)
    op.create_index(op.f("ix_tickets_priority"), "tickets", ["priority"], unique=False)
    op.create_index("ix_tickets_status_priority", "tickets", ["status", "priority"], unique=False)
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"], unique=False)
    op.create_index(
        op.f("ix_tickets_ticket_type"), "tickets", ["ticket_type"], unique=False
    )
    op.create_index(op.f("ix_tickets_user_id"), "tickets", ["user_id"], unique=False)

    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doc_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column(
            "doc_type",
            sa.String(length=64),
            nullable=False,
            comment="文档类型：refund_policy / support_rule 等",
        ),
        sa.Column(
            "audience_role",
            sa.String(length=32),
            nullable=False,
            comment="可见角色，M4 RBAC 会继续使用",
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_key"),
    )
    op.create_index(
        op.f("ix_knowledge_docs_audience_role"),
        "knowledge_docs",
        ["audience_role"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_docs_doc_type"), "knowledge_docs", ["doc_type"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_docs_status"), "knowledge_docs", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_knowledge_docs_title"), "knowledge_docs", ["title"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_docs_title"), table_name="knowledge_docs")
    op.drop_index(op.f("ix_knowledge_docs_status"), table_name="knowledge_docs")
    op.drop_index(op.f("ix_knowledge_docs_doc_type"), table_name="knowledge_docs")
    op.drop_index(op.f("ix_knowledge_docs_audience_role"), table_name="knowledge_docs")
    op.drop_table("knowledge_docs")

    op.drop_index(op.f("ix_tickets_user_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_ticket_type"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_status"), table_name="tickets")
    op.drop_index("ix_tickets_status_priority", table_name="tickets")
    op.drop_index(op.f("ix_tickets_priority"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_order_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_assigned_user_id"), table_name="tickets")
    op.drop_table("tickets")

    op.drop_index(op.f("ix_refunds_user_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_requested_at"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_refund_status"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_refund_reason"), table_name="refunds")
    op.drop_index("ix_refunds_reason_status", table_name="refunds")
    op.drop_index(op.f("ix_refunds_product_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.drop_table("refunds")

    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_order_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_product_id"), table_name="orders")
    op.drop_index("ix_orders_product_paid_at", table_name="orders")
    op.drop_index(op.f("ix_orders_paid_at"), table_name="orders")
    op.drop_index("ix_orders_paid_at_channel", table_name="orders")
    op.drop_index(op.f("ix_orders_channel_id"), table_name="orders")
    op.drop_table("orders")

    op.drop_index(op.f("ix_channels_status"), table_name="channels")
    op.drop_index(op.f("ix_channels_channel_type"), table_name="channels")
    op.drop_table("channels")

    op.drop_index(op.f("ix_products_status"), table_name="products")
    op.drop_index(op.f("ix_products_product_name"), table_name="products")
    op.drop_index(op.f("ix_products_category"), table_name="products")
    op.drop_table("products")

    op.drop_index(op.f("ix_users_status"), table_name="users")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_table("users")
