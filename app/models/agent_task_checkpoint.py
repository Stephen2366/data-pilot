"""M47 durable task checkpoint 与 append-only lifecycle event ORM。"""

from sqlalchemy import BigInteger, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentTaskCheckpoint(Base):
    """每个 task 一行当前快照；raw task id 不落库。"""

    __tablename__ = "agent_task_checkpoints"

    task_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_safe_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    active_role: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    state_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # M48：Context 与 state 同行、同 CAS transaction 更新；旧 0004 行允许为空。
    context_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_source_watermark: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    claim_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purge_after_us: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        Index("ix_agent_task_checkpoint_expiry", "status", "expires_at_us"),
        Index("ix_agent_task_checkpoint_purge", "purge_after_us"),
    )


class AgentTaskEvent(Base):
    """最小 typed 事件账；只存安全引用、版本和状态 identity。"""

    __tablename__ = "agent_task_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    event_identity: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    task_safe_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    version_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    state_identity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at_us: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (Index("ix_agent_task_event_task_version", "task_key", "version_after"),)
