from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    """System user/customer table used by RBAC and operations analysis."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="用户展示名")
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="RBAC 角色：admin / ops / customer_service / demo_user",
    )
    email: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, comment="敏感字段：邮箱"
    )
    phone: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment="敏感字段：手机号"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active", comment="用户状态"
    )

    orders = relationship("Order", back_populates="user")
    refunds = relationship("Refund", back_populates="user")
    tickets = relationship(
        "Ticket", back_populates="user", foreign_keys="Ticket.user_id"
    )
    assigned_tickets = relationship(
        "Ticket", back_populates="assigned_user", foreign_keys="Ticket.assigned_user_id"
    )
