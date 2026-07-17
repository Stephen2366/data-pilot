from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Refund(TimestampMixin, Base):
    """Refund fact table used for refund-rate and reason analysis."""

    __tablename__ = "refunds"
    __table_args__ = (
        Index("ix_refunds_reason_status", "refund_reason", "refund_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    refund_status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="退款状态：requested / approved / rejected / completed"
    )
    refund_reason: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="退款原因，例如 quality_issue"
    )
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    order = relationship("Order", back_populates="refunds")
    user = relationship("User", back_populates="refunds")
    product = relationship("Product", back_populates="refunds")
