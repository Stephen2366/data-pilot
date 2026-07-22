from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderItem(Base):
    """订单明细事实表。

    ★ 阶段二的 `orders.product_id` 等价于“一单一商品”。新增明细表后，一笔订单可以
    有 1-3 个商品，商品维度 GMV / 销量默认应从这里聚合，再回连订单头套用支付状态过滤。
    """

    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uk_order_line"),
        Index("ix_order_items_product", "product_id"),
        Index("ix_order_items_order_product", "order_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    item_discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    item_actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sku_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    order = relationship("Order", back_populates="order_items")
    product = relationship("Product", back_populates="order_items")
    refunds = relationship("Refund", back_populates="order_item")
