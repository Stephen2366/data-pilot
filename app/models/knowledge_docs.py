from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class KnowledgeDoc(TimestampMixin, Base):
    """Knowledge-base document table for later RAG and policy lookup."""

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="文档类型：refund_policy / support_rule 等"
    )
    audience_role: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="可见角色，M4 RBAC 会继续使用"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
