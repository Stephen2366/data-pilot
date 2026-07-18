from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class KnowledgeDoc(TimestampMixin, Base):
    """知识库文档表。

    ★ M1 先只建表和 seed 草稿文档；阶段三做 RAG 时，这张表会成为
    “政策 / 规则文本”的结构化入口。
    """

    __tablename__ = "knowledge_docs"

    # doc_key 是稳定业务编码，后续可用于同步外部文档或更新文档内容。
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # title 和 doc_type 用于检索、筛选和展示文档。
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="文档类型：refund_policy / support_rule 等",
    )
    # audience_role 预留给后续 RBAC：不同角色能看的政策文档可能不同。
    audience_role: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="可见角色，M4 RBAC 会继续使用"
    )
    # 只检索 active 文档，保留历史文档但不直接对用户展示。
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True, default="active"
    )
    # 文档正文先用 Text 存储，后续可再切分成 chunk 做向量检索。
    content: Mapped[str] = mapped_column(Text, nullable=False)
