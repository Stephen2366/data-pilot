from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Order(TimestampMixin, Base):
    """Order fact table, the main source for GMV and order-count metrics."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_paid_at_channel", "paid_at", "channel_id"),
        Index("ix_orders_product_paid_at", "product_id", "paid_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), nullable=False, index=True
    )
    order_status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="订单状态：paid / shipped / delivered / cancelled"
    )
    order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")
    channel = relationship("Channel", back_populates="orders")
    refunds = relationship("Refund", back_populates="order")
    tickets = relationship("Ticket", back_populates="order")
