from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Coupon(TimestampMixin, Base):
    """优惠券维表。

    ★ 优惠券和订单是多对多关系：一张券可被多笔订单使用，一笔订单也可能叠加多张券。
    这会逼后续 SQL 生成注意 `order_coupons` 桥接表和 `COUNT(DISTINCT orders.id)`。
    """

    __tablename__ = "coupons"
    __table_args__ = (
        Index("ix_valid_range", "valid_from", "valid_to"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coupon_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    coupon_name: Mapped[str] = mapped_column(String(120), nullable=False)
    coupon_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    min_order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    order_coupons = relationship("OrderCoupon", back_populates="coupon")
