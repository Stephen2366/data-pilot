from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderWide(Base):
    """订单宽表快照。

    ★ 宽表把订单、用户、商品、渠道常用字段冗余到一张表。它适合看板快速聚合，
    但不适合明细追溯或强一致校验；这个取舍正是 Phase 3A 的选表挑战之一。
    """

    __tablename__ = "orders_wide"
    __table_args__ = (
        UniqueConstraint("order_id", name="uk_orders_wide_order_id"),
        Index("ix_orders_wide_paid_channel", "paid_at", "channel_id"),
        Index("ix_orders_wide_category", "category"),
        Index("ix_orders_wide_batch", "batch_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_order_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_order_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(80), nullable=False)
    user_status: Mapped[str] = mapped_column(String(24), nullable=False)
    user_role: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_product_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    channel_code: Mapped[str] = mapped_column(String(48), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(48), nullable=False)
    order_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    refund_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_refund: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    has_refund: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
