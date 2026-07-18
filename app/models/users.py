from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    """系统用户 / 客户表。

    ★ 新手理解：这张表既是“谁在系统里操作”的账号表，也是“谁下了订单”的
    客户表。后续做 RBAC 权限控制时，会用 role 判断用户能不能看敏感数据。
    """

    __tablename__ = "users"

    # 主键：每个用户一行，用自增整数方便其他表做外键关联。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户展示名：用于页面展示和测试数据阅读，不作为登录凭证。
    user_name: Mapped[str] = mapped_column(String(80), nullable=False, comment="用户展示名")
    # 角色字段：M4 的 RBAC 会继续使用。加索引是因为查询经常按角色过滤。
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="RBAC 角色：admin / ops / customer_service / demo_user",
    )
    # 敏感字段：邮箱和手机号后续会进入 SQL Guard 的敏感字段拦截规则。
    email: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, comment="敏感字段：邮箱"
    )
    phone: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, comment="敏感字段：手机号"
    )
    # 状态字段：保留 disabled 用户，方便后续接口演示状态筛选。
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active", comment="用户状态"
    )

    # 关系字段 ================================================================
    # relationship 不会新增数据库列，它只是告诉 ORM：这些表可以通过外键互相导航。
    orders = relationship("Order", back_populates="user")
    refunds = relationship("Refund", back_populates="user")
    # Ticket 有两个 users 外键：提交人和处理客服，所以必须用 foreign_keys 明确说明。
    tickets = relationship(
        "Ticket", back_populates="user", foreign_keys="Ticket.user_id"
    )
    assigned_tickets = relationship(
        "Ticket", back_populates="assigned_user", foreign_keys="Ticket.assigned_user_id"
    )
