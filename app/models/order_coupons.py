from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrderCoupon(Base):
    """订单-优惠券桥接表。

    ★ 桥接表是多对多关系的实体化表达。后续按券统计订单数时，如果直接 `COUNT(*)`
    容易把一单多券放大，所以 relations.yaml 会专门写 aggregation_warning。
    """

    __tablename__ = "order_coupons"
    __table_args__ = (
        UniqueConstraint("order_id", "coupon_id", name="uk_order_coupon"),
        Index("ix_order_coupons_coupon_order", "coupon_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id"), nullable=False, index=True)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    order = relationship("Order", back_populates="order_coupons")
    coupon = relationship("Coupon", back_populates="order_coupons")
