from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Refund(TimestampMixin, Base):
    """退款事实表。

    ★ 退款表是订单的“售后事实”。它既能统计退款金额和原因，也能和订单表
    组合计算商品退款率：退款数 / 订单数。
    """

    __tablename__ = "refunds"
    __table_args__ = (
        # Top 退款原因和状态筛选经常一起出现，组合索引能服务这类查询。
        Index("ix_refunds_reason_status", "refund_reason", "refund_status"),
    )

    # refund_no 是业务单号，id 是数据库主键；二者分开更适合后续扩展。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refund_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 同时冗余 user_id / product_id，是为了退款分析时减少不必要的多表跳转。
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    # 状态与原因是退款分析的两个常见维度。
    refund_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="退款状态：requested / approved / rejected / completed",
    )
    refund_reason: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="退款原因，例如 quality_issue"
    )
    # 退款金额同样使用 Numeric，避免金额计算出现浮点误差。
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # requested_at 用于按申请时间统计退款趋势；processed_at 可为空表示尚未处理。
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关系字段：退款可以回查对应订单、用户和商品。
    order = relationship("Order", back_populates="refunds")
    user = relationship("User", back_populates="refunds")
    product = relationship("Product", back_populates="refunds")
