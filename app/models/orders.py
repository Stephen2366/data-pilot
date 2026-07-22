from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Order(TimestampMixin, Base):
    """订单事实表。

    ★ 事实表记录“发生了什么”。订单是 GMV、订单量、渠道分析、商品分析的
    核心事实表，后续大多数 SQL 分析都会从这张表开始。
    """

    __tablename__ = "orders"
    __table_args__ = (
        # 常见查询 1：按时间范围 + 渠道统计 GMV / 订单量。
        Index("ix_orders_paid_at_channel", "paid_at", "channel_id"),
        # 常见查询 2：按商品 + 时间范围统计销量或退款率分母。
        Index("ix_orders_product_paid_at", "product_id", "paid_at"),
    )

    # 主键与业务单号分开：id 适合做外键，order_no 适合给用户或客服查看。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 源系统单号允许重复，用来模拟真实企业里“外部单号不干净”的逻辑脏数据。
    source_order_no: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    external_order_no: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # 三个外键把订单连接到“谁买的、买了什么、从哪个渠道来”。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), nullable=False, index=True
    )
    # 订单状态会影响 GMV 口径，例如已取消订单通常不计入 GMV。
    order_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="订单状态：paid / shipped / delivered / cancelled",
    )
    # 金额字段使用 Decimal / Numeric，适合财务类精确计算。
    order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 支付时间可为空：未支付订单仍可存在，但 GMV 默认必须排除 paid_at IS NULL。
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # 关系字段 ================================================================
    # 多对一：多笔订单属于同一个用户 / 商品 / 渠道。
    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")
    channel = relationship("Channel", back_populates="orders")
    # 一对多：一笔订单后续可能有明细、优惠券、退款记录或客服工单。
    order_items = relationship("OrderItem", back_populates="order")
    order_coupons = relationship("OrderCoupon", back_populates="order")
    refunds = relationship("Refund", back_populates="order")
    tickets = relationship("Ticket", back_populates="order")
