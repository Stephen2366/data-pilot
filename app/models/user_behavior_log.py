from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserBehaviorLog(Base):
    """用户行为事件日志。

    ★ 这是典型大表：每一行是一条事件，不是一笔订单。它用来训练 agent 区分
    订单聚合和漏斗分析，例如 view_product -> add_to_cart -> payment_success。
    """

    __tablename__ = "user_behavior_log"
    __table_args__ = (
        Index("ix_behavior_event_time_type", "event_time", "event_type"),
        Index("ix_behavior_session_event", "session_id", "event_type"),
        Index("ix_behavior_device_event", "device_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    page_url: Mapped[str | None] = mapped_column(String(240), nullable=True)
    referrer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="behavior_logs")
    product = relationship("Product", back_populates="behavior_logs")
    channel = relationship("Channel", back_populates="behavior_logs")
