"""M47-C：MySQL/InnoDB durable TaskBoundary adapter。

每个方法只开启一个短事务；claim/commit 都由数据库条件 UPDATE 决定胜者，Python 锁不参与
跨 worker 正确性。SQLite 仅用于确定性单测，产品默认明确为 MySQL。
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Callable, Mapping
from uuid import uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

# 先加载 Base 完成既有 models package 的集中注册，避免直接子模块导入触发循环。
from app.db.base import Base as _Base  # noqa: F401
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.governance import TrustedCaller
from engine.phase4b.identity import canonical_hash
from engine.phase4b.task_boundary import (
    TaskBoundary, TaskBoundaryError, TaskBoundaryEvent, TaskLifecycleFact, TaskProjection,
)
from engine.phase4b.task_runtime import TaskState
from engine.phase4b.task_state_codec import TaskStateCodec, TaskStateCodecError

_CHECKPOINT = AgentTaskCheckpoint.__table__
_EVENT = AgentTaskEvent.__table__
_TERMINAL = frozenset({"cancelled", "switched", "cleared", "expired"})


class MySQLTaskBoundary:
    """共享数据库上的 durable owner/version/TTL/CAS 边界。"""

    def __init__(
        self, engine: Engine, *, ttl_seconds: int = 900, tombstone_retention_seconds: int = 86400,
        max_state_bytes: int = 65536, clock: Callable[[], datetime] | None = None,
    ) -> None:
        """注入共享 Engine、TTL/retention 上限与可控时钟。"""

        self._engine = engine
        self._ttl_seconds = ttl_seconds
        self._retention_seconds = tombstone_retention_seconds
        self._codec = TaskStateCodec(max_bytes=max_state_bytes)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def runtime_identity(self) -> dict[str, object]:
        """返回 API/Trace 可对账且不含连接凭据的 durable runtime 事实。"""

        return {
            "identity": "phase4b-mysql-task-boundary-v1", "durability": "database_durable",
            "backend": self._engine.dialect.name, "ttl_seconds": self._ttl_seconds,
            "tombstone_retention_seconds": self._retention_seconds,
            "atomic_claim_commit": True, "state_schema_version": self._codec.schema_version,
        }

    def start(self, *, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """在一个短事务内签发 version=1 checkpoint 与 started event。"""

        owner, tenant, role = TaskBoundary.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        payload = self._encode(state)
        now_us = self._now_us()
        for _ in range(3):
            task_id = uuid4().hex
            key = self._task_key(task_id)
            row = {
                "task_key": key, "task_safe_ref": TaskBoundary.safe_ref(task_id), "owner_ref": owner, "tenant_ref": tenant, "active_role": role,
                "version": 1, "status": "active", "state_version": state.state_version,
                "state_identity": state.identity, "state_payload": payload, "claim_token_hash": None,
                "expires_at_us": now_us + self._ttl_seconds * 1_000_000, "purge_after_us": None,
                "created_at_us": now_us, "updated_at_us": now_us,
            }
            fact = self._fact(task_id, "started", "task_started", None, 1, state.identity)
            try:
                with self._engine.begin() as connection:
                    connection.execute(insert(_CHECKPOINT).values(**row))
                    self._append_event(connection, key, fact, event, now_us)
                return self._projection(task_id, row, state), fact
            except SQLAlchemyError as exc:
                if "unique" not in str(exc).lower() and "duplicate" not in str(exc).lower():
                    raise self._storage_error(exc) from exc
        raise TaskBoundaryError("task_storage_unavailable", "无法签发唯一 task")

    def claim(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> TaskProjection:
        """由数据库条件 UPDATE 决定唯一 winner，并签发单次 claim capability。"""

        owner, tenant, role = TaskBoundary.owner_scope(caller, active_role)
        key, now_us = self._task_key(task_id), self._now_us()
        token = secrets.token_urlsafe(32)
        token_hash = sha256(token.encode()).hexdigest()
        try:
            failure: TaskBoundaryError | None = None
            row = None
            with self._engine.begin() as connection:
                result = connection.execute(
                    update(_CHECKPOINT).where(
                        _CHECKPOINT.c.task_key == key, _CHECKPOINT.c.owner_ref == owner,
                        _CHECKPOINT.c.tenant_ref == tenant, _CHECKPOINT.c.active_role == role,
                        _CHECKPOINT.c.version == expected_version, _CHECKPOINT.c.status == "active",
                        _CHECKPOINT.c.expires_at_us > now_us,
                    ).values(version=expected_version + 1, status="claimed", claim_token_hash=token_hash, updated_at_us=now_us)
                )
                if result.rowcount != 1:
                    failure = self._classify_claim_failure(connection, key, owner, tenant, role, expected_version, now_us, task_id)
                else:
                    row = connection.execute(select(_CHECKPOINT).where(_CHECKPOINT.c.task_key == key)).mappings().one()
                    self._append_event(connection, key, self._fact(task_id, "claimed", "task_claimed", expected_version, expected_version + 1, row["state_identity"]), None, now_us)
            if failure is not None:
                raise failure
            assert row is not None
            state = self._decode(row["state_payload"])
            return self._projection(task_id, row, state, claim_token=token)
        except TaskBoundaryError:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def commit(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, terminal_status: str | None = None, active_role: str | None = None, event: TaskBoundaryEvent | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """仅允许未过期、版本/token 都匹配的 winner 提交下一版本。"""

        owner, tenant, role = TaskBoundary.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        status = terminal_status if terminal_status in {"cancelled", "switched", "cleared"} else "active"
        payload = self._encode(state)
        token_hash = sha256((claim.claim_token or "").encode()).hexdigest()
        now_us = self._now_us()
        after = claim.task_version + 1
        fact = self._fact(claim.task_id, status, f"task_{status}", claim.task_version - 1, after, state.identity)
        values: dict[str, Any] = {
            "version": after, "status": status, "state_identity": state.identity,
            "claim_token_hash": None, "updated_at_us": now_us,
        }
        if status == "active":
            values.update(state_payload=payload, expires_at_us=now_us + self._ttl_seconds * 1_000_000, purge_after_us=None)
        else:
            values.update(state_payload=None, purge_after_us=now_us + self._retention_seconds * 1_000_000)
        try:
            failure: TaskBoundaryError | None = None
            with self._engine.begin() as connection:
                result = connection.execute(update(_CHECKPOINT).where(
                    _CHECKPOINT.c.task_key == self._task_key(claim.task_id),
                    _CHECKPOINT.c.owner_ref == owner, _CHECKPOINT.c.tenant_ref == tenant,
                    _CHECKPOINT.c.active_role == role, _CHECKPOINT.c.version == claim.task_version,
                    _CHECKPOINT.c.status == "claimed", _CHECKPOINT.c.claim_token_hash == token_hash,
                    _CHECKPOINT.c.expires_at_us > now_us,
                ).values(**values))
                if result.rowcount != 1:
                    failure = self._classify_commit_failure(connection, self._task_key(claim.task_id), owner, tenant, role, claim, now_us)
                else:
                    self._append_event(connection, self._task_key(claim.task_id), fact, event, now_us)
            if failure is not None:
                raise failure
        except TaskBoundaryError:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc
        projection_row = {**values, "expires_at_us": values.get("expires_at_us", int(claim.expires_at.timestamp() * 1_000_000))}
        return self._projection(claim.task_id, projection_row, state), fact

    def clear(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """以 claim→terminal commit 复用同一 fencing，并立即擦除持久 payload。"""

        claim = self.claim(task_id=task_id, expected_version=expected_version, caller=caller, active_role=active_role)
        evidence = tuple(replace(item, validity="invalidated", invalidation_reason="task_cleared") if item.validity == "active" else item for item in claim.state.evidence)
        state = replace(claim.state, status="cleared", termination="cleared_by_caller", evidence=evidence)
        return self.commit(claim=claim, caller=caller, state=state, terminal_status="cleared", active_role=active_role)

    def switch(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """同一事务原子退休旧 task 并创建新 task。"""

        owner, tenant, role = TaskBoundary.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        payload, now_us = self._encode(state), self._now_us()
        token_hash = sha256((claim.claim_token or "").encode()).hexdigest()
        new_id, new_key = uuid4().hex, ""
        try:
            failure: TaskBoundaryError | None = None
            with self._engine.begin() as connection:
                result = connection.execute(update(_CHECKPOINT).where(
                    _CHECKPOINT.c.task_key == self._task_key(claim.task_id),
                    _CHECKPOINT.c.owner_ref == owner, _CHECKPOINT.c.tenant_ref == tenant,
                    _CHECKPOINT.c.active_role == role, _CHECKPOINT.c.version == claim.task_version,
                    _CHECKPOINT.c.status == "claimed", _CHECKPOINT.c.claim_token_hash == token_hash,
                    _CHECKPOINT.c.expires_at_us > now_us,
                ).values(version=claim.task_version + 1, status="switched", state_payload=None,
                         state_identity=claim.state.identity, claim_token_hash=None, updated_at_us=now_us,
                         purge_after_us=now_us + self._retention_seconds * 1_000_000))
                if result.rowcount != 1:
                    failure = self._classify_commit_failure(connection, self._task_key(claim.task_id), owner, tenant, role, claim, now_us)
                else:
                    new_key = self._task_key(new_id)
                    connection.execute(insert(_CHECKPOINT).values(
                        task_key=new_key, task_safe_ref=TaskBoundary.safe_ref(new_id), owner_ref=owner, tenant_ref=tenant, active_role=role,
                        version=1, status="active", state_version=state.state_version,
                        state_identity=state.identity, state_payload=payload, claim_token_hash=None,
                        expires_at_us=now_us + self._ttl_seconds * 1_000_000, purge_after_us=None,
                        created_at_us=now_us, updated_at_us=now_us,
                    ))
                    fact = TaskLifecycleFact(TaskBoundary.safe_ref(new_id), "switched", "task_switched", claim.task_version - 1, 1, state.identity, previous_task_safe_ref=TaskBoundary.safe_ref(claim.task_id), resume_source="database")
                    self._append_event(connection, new_key, fact, event, now_us)
            if failure is not None:
                raise failure
        except TaskBoundaryError:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc
        return TaskProjection(new_id, 1, state, "active", self._from_us(now_us + self._ttl_seconds * 1_000_000)), fact

    def purge_tombstones(self, *, limit: int = 100) -> int:
        """每次只清理有限行，避免维护事务长期占锁。"""

        now_us = self._now_us()
        self.expire_stale(limit=limit)
        try:
            with self._engine.begin() as connection:
                keys = list(connection.execute(select(_CHECKPOINT.c.task_key).where(
                    _CHECKPOINT.c.purge_after_us.is_not(None), _CHECKPOINT.c.purge_after_us <= now_us,
                ).order_by(_CHECKPOINT.c.purge_after_us).limit(limit)).scalars())
                if not keys:
                    return 0
                connection.execute(delete(_EVENT).where(_EVENT.c.task_key.in_(keys)))
                return int(connection.execute(delete(_CHECKPOINT).where(_CHECKPOINT.c.task_key.in_(keys))).rowcount or 0)
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def expire_stale(self, *, limit: int = 100) -> int:
        """把无人访问的 active/claimed 过期行先擦成 tombstone，并补齐 typed event。"""

        now_us = self._now_us()
        try:
            with self._engine.begin() as connection:
                rows = connection.execute(select(_CHECKPOINT).where(
                    _CHECKPOINT.c.status.in_(("active", "claimed")), _CHECKPOINT.c.expires_at_us <= now_us,
                ).order_by(_CHECKPOINT.c.expires_at_us).limit(limit).with_for_update()).mappings().all()
                changed = 0
                for row in rows:
                    result = connection.execute(update(_CHECKPOINT).where(
                        _CHECKPOINT.c.task_key == row["task_key"], _CHECKPOINT.c.version == row["version"],
                        _CHECKPOINT.c.status == row["status"],
                    ).values(status="expired", state_payload=None, claim_token_hash=None,
                             purge_after_us=row["expires_at_us"] + self._retention_seconds * 1_000_000,
                             updated_at_us=now_us))
                    if result.rowcount == 1:
                        fact = TaskLifecycleFact(row["task_safe_ref"], "expired", "task_expired", row["version"], row["version"], row["state_identity"], resume_source="database")
                        self._append_event(connection, row["task_key"], fact, None, now_us)
                        changed += 1
                return changed
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def close(self) -> None:
        """应用 lifespan 结束时释放本 adapter 自有连接池。"""

        self._engine.dispose()

    def lifecycle_rejection(self, task_id: str, reason_code: str) -> TaskLifecycleFact:
        """为拒绝路径生成不暴露 raw task id 的 database lifecycle 事实。"""

        return TaskLifecycleFact(TaskBoundary.safe_ref(task_id), "rejected", reason_code, None, None, None, resume_source="database", storage_outcome="rejected")

    @staticmethod
    def owner_ref(caller: TrustedCaller | None) -> str:
        """复用 memory adapter 的稳定 owner hash 算法。"""

        return TaskBoundary.owner_ref(caller)

    def _classify_claim_failure(self, connection: Any, key: str, owner: str, tenant: str, role: str, expected: int, now_us: int, task_id: str) -> TaskBoundaryError:
        """在 CAS loser 事务中安全区分 owner、expiry、status 与 version。"""

        row = connection.execute(select(_CHECKPOINT).where(_CHECKPOINT.c.task_key == key)).mappings().first()
        if row is None or row["owner_ref"] != owner or row["tenant_ref"] != tenant or row["active_role"] != role:
            return TaskBoundaryError("task_unavailable", "task 不存在或不属于 caller", safety_status="blocked")
        if row["status"] in {"active", "claimed"} and row["expires_at_us"] <= now_us:
            fact = self._fact(task_id, "expired", "task_expired", row["version"], row["version"], row["state_identity"])
            result = connection.execute(update(_CHECKPOINT).where(
                _CHECKPOINT.c.task_key == key, _CHECKPOINT.c.status == row["status"],
                _CHECKPOINT.c.version == row["version"],
            ).values(
                status="expired", state_payload=None, claim_token_hash=None, purge_after_us=row["expires_at_us"] + self._retention_seconds * 1_000_000, updated_at_us=now_us,
            ))
            if result.rowcount == 1:
                self._append_event(connection, key, fact, None, now_us)
            return TaskBoundaryError("task_expired", "task 已过期")
        if row["status"] != "active":
            return TaskBoundaryError("task_not_active", "task 已结束")
        if row["version"] != expected:
            return TaskBoundaryError("task_version_conflict", "task version 已变化")
        return TaskBoundaryError("task_version_conflict", "claim 竞争失败")

    def _classify_commit_failure(self, connection: Any, key: str, owner: str, tenant: str, role: str, claim: TaskProjection, now_us: int) -> TaskBoundaryError:
        """在同一事务内把过期 claim 擦除；其他失配统一按安全失败返回。"""

        row = connection.execute(select(_CHECKPOINT).where(_CHECKPOINT.c.task_key == key)).mappings().first()
        if row is None or row["owner_ref"] != owner or row["tenant_ref"] != tenant or row["active_role"] != role:
            return TaskBoundaryError("task_unavailable", "task 不存在或不属于 caller", safety_status="blocked")
        if row["status"] == "claimed" and row["expires_at_us"] <= now_us:
            fact = TaskLifecycleFact(row["task_safe_ref"], "expired", "task_expired", row["version"], row["version"], row["state_identity"], resume_source="database")
            result = connection.execute(update(_CHECKPOINT).where(
                _CHECKPOINT.c.task_key == key, _CHECKPOINT.c.status == "claimed",
                _CHECKPOINT.c.version == row["version"],
            ).values(status="expired", state_payload=None, claim_token_hash=None,
                     purge_after_us=row["expires_at_us"] + self._retention_seconds * 1_000_000,
                     updated_at_us=now_us))
            if result.rowcount == 1:
                self._append_event(connection, key, fact, None, now_us)
            return TaskBoundaryError("task_expired", "claim 已过期")
        return TaskBoundaryError("task_version_conflict", "claim 已失效")

    def _append_event(self, connection: Any, key: str, fact: TaskLifecycleFact, event: TaskBoundaryEvent | None, now_us: int) -> None:
        """在 checkpoint 同一事务追加最小 typed event。"""

        payload = event.safe_projection() if event else TaskBoundaryEvent().safe_projection()
        identity = canonical_hash({"fact": fact.safe_projection(), "event": payload, "nonce": uuid4().hex})
        connection.execute(insert(_EVENT).values(
            event_schema_version="phase4b-task-boundary-event-v1", event_identity=identity,
            task_key=key, task_safe_ref=fact.task_safe_ref, action=fact.action,
            reason_code=fact.reason_code, version_before=fact.version_before,
            version_after=fact.version_after, state_identity=fact.state_identity,
            event_payload=payload, created_at_us=now_us,
        ))

    def _encode(self, state: TaskState) -> dict[str, Any]:
        """把 codec 错误映射成 boundary 的稳定 fail-closed reason。"""

        try:
            return self._codec.encode(state)
        except TaskStateCodecError as exc:
            raise TaskBoundaryError(exc.reason_code, str(exc), safety_status="blocked") from exc

    def _decode(self, payload: Any) -> TaskState:
        """恢复数据库 payload，并隐藏底层 schema 异常细节。"""

        try:
            return self._codec.decode(payload)
        except TaskStateCodecError as exc:
            raise TaskBoundaryError(exc.reason_code, str(exc), safety_status="blocked") from exc

    def _projection(self, task_id: str, row: Mapping[str, Any], state: TaskState, *, claim_token: str | None = None) -> TaskProjection:
        """把数据库行收窄为合法 owner 可见投影。"""

        return TaskProjection(task_id, int(row["version"]), state, str(row["status"]), self._from_us(int(row["expires_at_us"])), claim_token)

    @staticmethod
    def _task_key(task_id: str) -> str:
        """把 raw task id 转为数据库 lookup key。"""

        return sha256(task_id.encode()).hexdigest()

    def _fact(self, task_id: str, action: str, reason: str, before: int | None, after: int | None, state_identity: str | None) -> TaskLifecycleFact:
        """从 raw id 单向生成 lifecycle safe ref。"""

        return TaskLifecycleFact(TaskBoundary.safe_ref(task_id), action, reason, before, after, state_identity, resume_source="database")

    def _now_us(self) -> int:
        """读取 timezone-aware 时钟并转换为跨数据库一致的 epoch 微秒。"""

        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("task boundary clock 必须带 timezone")
        return int(value.timestamp() * 1_000_000)

    @staticmethod
    def _from_us(value: int) -> datetime:
        """把 epoch 微秒恢复为 UTC datetime 供 API 投影。"""

        return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc)

    @staticmethod
    def _storage_error(exc: SQLAlchemyError) -> TaskBoundaryError:
        """隐藏驱动/SQL 正文，只公开稳定的 storage unavailable。"""

        return TaskBoundaryError("task_storage_unavailable", exc.__class__.__name__, safety_status="blocked")
