from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductPriceHistory(Base):
    """商品价格历史表（SCD Type 2）。

    ★ `products.price` 只表示当前价；如果用户问“6 月当时售价 / 历史均价”，需要用
    `valid_from`、`valid_to` 做时间窗口 JOIN，这就是 SCD Type 2 的核心。
    """

    __tablename__ = "product_price_history"
    __table_args__ = (
        Index("ix_price_history_product_window", "product_id", "valid_from", "valid_to"),
        Index("ix_price_history_current", "product_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    price_source: Mapped[str] = mapped_column(String(48), nullable=False, default="seed")
    change_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    product = relationship("Product", back_populates="price_history")
