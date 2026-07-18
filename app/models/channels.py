from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Channel(TimestampMixin, Base):
    """销售 / 获客渠道维表。

    ★ 渠道维表回答“订单从哪里来”：例如 App、自营网页、平台店、付费投放。
    后续分析渠道订单量和 GMV 时，会从 orders.channel_id 关联到这里。
    """

    __tablename__ = "channels"

    # 主键：数据库内部使用；channel_code 是业务上更稳定的渠道编码。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    channel_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # 渠道类型用于分组分析，例如 owned / marketplace / paid / partner。
    channel_type: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        index=True,
        comment="渠道类型，如 paid / organic / partner",
    )
    # 状态字段让后续接口可以过滤停用渠道。
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )

    # 一个渠道可以带来多笔订单。
    orders = relationship("Order", back_populates="channel")
