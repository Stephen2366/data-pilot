from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Channel(TimestampMixin, Base):
    """Sales/acquisition channel dimension table."""

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    channel_name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel_type: Mapped[str] = mapped_column(
        String(48), nullable=False, index=True, comment="渠道类型，如 paid / organic / partner"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )

    orders = relationship("Order", back_populates="channel")
