from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Product(TimestampMixin, Base):
    """商品维表。

    ★ 维表可以类比成“字典表”：它描述商品是谁、属于什么类目、当前是否在售；
    订单和退款事实表会通过 product_id 指向这里。
    """

    __tablename__ = "products"

    # 主键：商品在数据库里的稳定身份，其他表通过 product_id 关联。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SKU 是业务系统里的商品编码，设置 unique 避免同一个商品编码重复入库。
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 商品名 / 类目常用于筛选、分组和展示，因此加索引提高查询效率。
    product_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    # category_id 是新库的规范化类目外键；category 字符串保留为历史冗余字段，兼容旧 API / SQL。
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_categories.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # 商品状态保留 paused 等非 active 数据，后续 API 可以演示状态筛选。
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )
    # 价格使用 Decimal + Numeric，避免 float 小数误差影响金额类计算。
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # 上架时间可为空：有些历史或测试商品可能没有明确上架时间。
    launched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关系字段：商品可以出现在多笔订单、订单明细、退款和行为日志中。
    category_ref = relationship("ProductCategory", back_populates="products")
    orders = relationship("Order", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    refunds = relationship("Refund", back_populates="product")
    behavior_logs = relationship("UserBehaviorLog", back_populates="product")
    price_history = relationship("ProductPriceHistory", back_populates="product")
