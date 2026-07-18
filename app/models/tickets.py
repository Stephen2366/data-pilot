from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Ticket(TimestampMixin, Base):
    """客服工单事实表。

    ★ 工单记录“用户向客服反馈了什么问题”。它服务客服工作量、优先级、
    处理状态等分析，也给后续 RAG 政策问答提供业务场景。
    """

    __tablename__ = "tickets"
    __table_args__ = (
        # 客服列表常按“待处理 + 高优先级”筛选，所以 status + priority 建组合索引。
        Index("ix_tickets_status_priority", "status", "priority"),
    )

    # ticket_no 是业务可见单号，id 是数据库内部主键。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # user_id 是提交工单的人；order_id 可为空，因为有些咨询不绑定具体订单。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id"), nullable=True, index=True
    )
    # assigned_user_id 指向处理客服，也来自 users 表。
    assigned_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # 类型、优先级、状态是客服运营分析最常用的筛选条件。
    ticket_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        index=True,
        comment="优先级：low / medium / high / urgent",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="工单状态：pending / processing / resolved / closed",
    )
    # subject / description 暂时只做文本字段；后续 RAG 可以考虑抽取知识或摘要。
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 未解决工单没有 resolved_at，因此允许为空。
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 关系字段 ================================================================
    # 同一张 users 表被关联两次，所以 user 和 assigned_user 都要明确 foreign_keys。
    user = relationship("User", back_populates="tickets", foreign_keys=[user_id])
    order = relationship("Order", back_populates="tickets")
    assigned_user = relationship(
        "User", back_populates="assigned_tickets", foreign_keys=[assigned_user_id]
    )
