from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """复用的创建 / 更新时间字段。

    ★ Mixin 可以理解成“公共字段模板”：每张业务表都需要 created_at /
    updated_at，就把它们抽到这里，避免 7 个模型重复写同样的列。
    """

    # ★ server_default 让数据库自己填创建时间；应用侧不传值也能有时间戳。
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    # ★ onupdate 只在 ORM 发起更新时刷新；如果裸 SQL 更新，需由 SQL 自己维护。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
