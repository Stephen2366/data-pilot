from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Product(TimestampMixin, Base):
    """Product dimension table for GMV, refund and category analysis."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    product_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    launched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    orders = relationship("Order", back_populates="product")
    refunds = relationship("Refund", back_populates="product")
