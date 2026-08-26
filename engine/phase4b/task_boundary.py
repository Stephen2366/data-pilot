"""M43-C：TaskState 的进程内安全边界。

这是可替换 adapter seam，不冒充 durable checkpoint。owner、TTL、version 与 claim/commit
都在锁内检查；未知 task 和错误 owner 统一返回 ``task_unavailable``。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import RLock
from typing import Any, Callable, Literal, Mapping, Protocol
from uuid import uuid4

from engine.governance import TrustedCaller
from engine.phase4b.task_context import TaskContextWindow
from engine.phase4b.task_runtime import TaskState


class TaskBoundaryError(ValueError):
    """Task lifecycle 的稳定失败；reason/safety 可直接投影为安全拒绝。"""

    def __init__(self, reason_code: str, message: str, *, safety_status: Literal["passed", "blocked"] = "passed") -> None:
        """保存可安全投影的 reason/safety，并把内部说明留在异常文本。"""

        self.reason_code, self.safety_status = reason_code, safety_status
        super().__init__(f"{reason_code}: {message}")


@dataclass(frozen=True)
class TaskProjection:
    """仅返回给合法 owner 的 task 快照；raw id 不写入长期 Trace。"""

    task_id: str
    task_version: int
    state: TaskState
    status: str
    expires_at: datetime
    # ★ 单次 claim capability 只在进程内传给 commit，永不进入 API/Trace。
    claim_token: str | None = field(default=None, repr=False, compare=False)
    context: TaskContextWindow | None = field(default=None, repr=False)

    def safe_projection(self) -> dict[str, object]:
        """省略单次 claim token，只公开 owner 可见 task 快照。"""

        return {
            "task_id": self.task_id, "task_version": self.task_version,
            "state": self.state.safe_projection(), "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "context": self.context.safe_projection() if self.context else None,
        }


@dataclass(frozen=True)
class TaskLifecycleFact:
    """API/Trace/Eval 共用的不可逆生命周期事实。"""

    task_safe_ref: str
    action: str
    reason_code: str
    version_before: int | None
    version_after: int | None
    state_identity: str | None
    previous_task_safe_ref: str | None = None
    checkpoint_safe_ref: str | None = None
    resume_source: str = "memory"
    storage_outcome: str = "committed"
    schema_version: str = "phase4b-task-boundary-event-v1"

    def safe_projection(self) -> dict[str, object]:
        """返回 API/Trace/Eval 共用且不含 raw task id 的 lifecycle 形状。"""

        return {"task_safe_ref": self.task_safe_ref, "action": self.action, "reason_code": self.reason_code, "version_before": self.version_before, "version_after": self.version_after, "state_identity": self.state_identity, "previous_task_safe_ref": self.previous_task_safe_ref, "checkpoint_safe_ref": self.checkpoint_safe_ref or self.task_safe_ref, "resume_source": self.resume_source, "storage_outcome": self.storage_outcome, "schema_version": self.schema_version}


@dataclass(frozen=True)
class TaskBoundaryEvent:
    """可写入 event ledger 的 closed-world turn 摘要。"""

    delta_category: str | None = None
    transition_identity: str | None = None
    action_count: int | None = None
    termination_reason: str | None = None
    turn_ordinal: int | None = None
    state_identity: str | None = None
    constraint_keys: tuple[str, ...] = ()
    requirement_identities: tuple[str, ...] = ()
    active_evidence_identities: tuple[str, ...] = ()
    budget_identity: str | None = None
    context_identity: str | None = None
    compact_identity: str | None = None
    schema_version: str = "phase4b-task-boundary-event-v1"

    def safe_projection(self) -> dict[str, object]:
        """投影 event ledger 允许的最小 turn 字段。"""

        base = {
            "delta_category": self.delta_category, "transition_identity": self.transition_identity,
            "action_count": self.action_count, "termination_reason": self.termination_reason,
        }
        if self.schema_version == "phase4b-task-boundary-event-v1":
            return base
        return {
            **base, "turn_ordinal": self.turn_ordinal, "state_identity": self.state_identity,
            "constraint_keys": list(self.constraint_keys),
            "requirement_identities": list(self.requirement_identities),
            "active_evidence_identities": list(self.active_evidence_identities),
            "budget_identity": self.budget_identity, "context_identity": self.context_identity,
            "compact_identity": self.compact_identity,
        }


class TaskBoundaryPort(Protocol):
    """Task turn 依赖的最小 adapter seam；memory/MySQL 必须同语义。"""

    @property
    def runtime_identity(self) -> Mapping[str, object]: ...
    def start(self, *, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]: ...
    def claim(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> TaskProjection: ...
    def commit(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, terminal_status: str | None = None, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]: ...
    def clear(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> tuple[TaskProjection, TaskLifecycleFact]: ...
    def switch(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]: ...
    def lifecycle_rejection(self, task_id: str, reason_code: str) -> TaskLifecycleFact: ...
    @staticmethod
    def owner_ref(caller: TrustedCaller | None) -> str: ...


@dataclass(frozen=True)
class _Checkpoint:
    """manager 私有存储形状；claimed 是一次执行权，不能由客户端构造。"""

    task_id: str
    owner_ref: str
    tenant_ref: str
    active_role: str
    version: int
    status: Literal["claimed", "active", "cancelled", "switched", "cleared"]
    state: TaskState | None
    expires_at: datetime
    claim_token_hash: str | None = None
    context: TaskContextWindow | None = None


class TaskBoundary:
    """封装完整 task 生命周期；endpoint 不接触内部字典或 owner 比较值。"""

    def __init__(self, *, ttl_seconds: int = 1800, clock: Callable[[], datetime] | None = None) -> None:
        """创建仅供测试/兼容使用的进程内 parity adapter。"""

        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._items: dict[str, _Checkpoint] = {}
        self._lock = RLock()

    @property
    def runtime_identity(self) -> dict[str, object]:
        """明确宣告 process-local，防止 M43 被误报成 B5 durable state。"""

        return {"identity": "phase4b-in-memory-task-boundary-v1", "durability": "process_local_non_durable", "ttl_seconds": self._ttl_seconds, "atomic_claim_commit": True}

    def start(self, *, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """为可信 owner 签发一个 version=1 的新 task。"""

        owner, tenant, role = self.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        now = self._now()
        item = _Checkpoint(
            uuid4().hex, owner, tenant, role, 1, "active", state,
            now + timedelta(seconds=self._ttl_seconds), context=context or TaskContextWindow.empty(),
        )
        with self._lock:
            self._items[item.task_id] = item
        return self._projection(item), self._fact(item, "started", "task_started", None)

    def claim(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> TaskProjection:
        """以 owner/version/TTL compare-and-set 消费一次执行权。"""

        owner, tenant, role = self.owner_scope(caller, active_role)
        with self._lock:
            item = self._owned(task_id, owner, tenant, role)
            if self._now() >= item.expires_at:
                self._items[task_id] = replace(item, status="expired", state=None, claim_token_hash=None, context=None)
                raise TaskBoundaryError("task_expired", "task 已过期")
            if item.status != "active":
                raise TaskBoundaryError("task_not_active", "task 已结束")
            if item.version != expected_version:
                raise TaskBoundaryError("task_version_conflict", "task version 已变化")
            token = secrets.token_urlsafe(32)
            claimed = replace(item, version=item.version + 1, status="claimed", claim_token_hash=sha256(token.encode()).hexdigest())
            self._items[task_id] = claimed
        return self._projection(claimed, claim_token=token)

    def commit(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, terminal_status: str | None = None, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """只提交仍为当前版本的 claim；失败时绝不覆盖其他 turn。"""

        owner, tenant, role = self.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        with self._lock:
            item = self._owned(claim.task_id, owner, tenant, role)
            if self._now() >= item.expires_at:
                self._items[item.task_id] = replace(item, status="expired", state=None, claim_token_hash=None, context=None)
                raise TaskBoundaryError("task_expired", "claim 已过期")
            token_hash = sha256((claim.claim_token or "").encode()).hexdigest()
            if item.status != "claimed" or item.version != claim.task_version or not item.claim_token_hash or not secrets.compare_digest(item.claim_token_hash, token_hash):
                raise TaskBoundaryError("task_version_conflict", "claim 已失效")
            status = terminal_status if terminal_status in {"cancelled", "switched", "cleared"} else "active"
            committed = replace(
                item, version=item.version + 1, status=status, state=state,
                expires_at=self._now() + timedelta(seconds=self._ttl_seconds), claim_token_hash=None,
                context=context if context is not None else claim.context,
            )
            self._items[item.task_id] = committed if status == "active" else replace(committed, state=None, context=None)
        return self._projection(committed), self._fact(committed, status, f"task_{status}", claim.task_version - 1)

    def clear(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None, active_role: str | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """显式清理并使剩余 active Evidence 失效。"""

        claim = self.claim(task_id=task_id, expected_version=expected_version, caller=caller, active_role=active_role)
        evidence = tuple(
            replace(item, validity="invalidated", invalidation_reason="task_cleared")
            if item.validity == "active" else item
            for item in claim.state.evidence
        )
        state = replace(claim.state, status="cleared", termination="cleared_by_caller", evidence=evidence)
        return self.commit(claim=claim, caller=caller, state=state, terminal_status="cleared", active_role=active_role)

    def switch(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, active_role: str | None = None, event: TaskBoundaryEvent | None = None, context: TaskContextWindow | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """在同一把锁内终止旧 task 并签发新 task，避免出现只完成半边的切换。"""

        owner, tenant, role = self.owner_scope(caller, active_role)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        now = self._now()
        with self._lock:
            old = self._owned(claim.task_id, owner, tenant, role)
            if self._now() >= old.expires_at:
                self._items[old.task_id] = replace(old, status="expired", state=None, claim_token_hash=None, context=None)
                raise TaskBoundaryError("task_expired", "switch claim 已过期")
            token_hash = sha256((claim.claim_token or "").encode()).hexdigest()
            if old.status != "claimed" or old.version != claim.task_version or not old.claim_token_hash or not secrets.compare_digest(old.claim_token_hash, token_hash):
                raise TaskBoundaryError("task_version_conflict", "switch claim 已失效")
            retired_evidence = tuple(
                replace(item, validity="invalidated", invalidation_reason="task_switched")
                if item.validity == "active" else item
                for item in old.state.evidence
            )
            retired_state = replace(old.state, status="switched", termination="switched_by_caller", evidence=retired_evidence)
            self._items[old.task_id] = replace(old, version=old.version + 1, status="switched", state=None, claim_token_hash=None, context=None)
            new = _Checkpoint(
                uuid4().hex, owner, tenant, role, 1, "active", state,
                now + timedelta(seconds=self._ttl_seconds), context=context or TaskContextWindow.empty(),
            )
            self._items[new.task_id] = new
        lifecycle = TaskLifecycleFact(
            self.safe_ref(new.task_id), "switched", "task_switched", claim.task_version - 1, new.version,
            new.state.identity, previous_task_safe_ref=self.safe_ref(old.task_id),
        )
        return self._projection(new), lifecycle

    def lifecycle_rejection(self, task_id: str, reason_code: str) -> TaskLifecycleFact:
        """生成不暴露 raw task id 的统一拒绝事实。"""

        return TaskLifecycleFact(self.safe_ref(task_id), "rejected", reason_code, None, None, None)

    @staticmethod
    def owner_ref(caller: TrustedCaller | None) -> str:
        """把可信 caller 与 tenant 绑定为不可逆内部 owner 值。"""

        if caller is None:
            raise TaskBoundaryError("task_unavailable", "caller 不可信", safety_status="blocked")
        source = caller.thread_owner_ref or f"{caller.audit_ref}\0tenant:{caller.tenant_id or '-'}"
        return sha256(source.encode()).hexdigest()

    @classmethod
    def owner_scope(cls, caller: TrustedCaller | None, active_role: str | None) -> tuple[str, str, str]:
        """分别绑定 owner、tenant 与本 turn 生效角色，避免多角色权限漂移。"""

        if caller is None:
            raise TaskBoundaryError("task_unavailable", "caller 不可信", safety_status="blocked")
        role = active_role or (next(iter(caller.resolved_roles)) if len(caller.resolved_roles) == 1 else None)
        if role is None or role not in caller.resolved_roles:
            raise TaskBoundaryError("task_unavailable", "active role 不可信", safety_status="blocked")
        tenant = sha256(f"tenant:{caller.tenant_id or '-'}".encode()).hexdigest()
        return cls.owner_ref(caller), tenant, role

    @staticmethod
    def safe_ref(task_id: str) -> str:
        """为 Trace/Eval 计算不可恢复的 task 引用。"""

        return "task:" + sha256(task_id.encode()).hexdigest()

    def _owned(self, task_id: str, owner: str, tenant: str, role: str) -> _Checkpoint:
        """统一未知/错 owner 失败，避免 task 枚举侧信道。"""

        item = self._items.get(task_id)
        if item is None or not secrets.compare_digest(item.owner_ref, owner) or not secrets.compare_digest(item.tenant_ref, tenant) or not secrets.compare_digest(item.active_role, role):
            raise TaskBoundaryError("task_unavailable", "task 不存在或不属于 caller", safety_status="blocked")
        return item

    def _projection(self, item: _Checkpoint, *, claim_token: str | None = None) -> TaskProjection:
        """把私有 checkpoint 收窄为 owner 可见投影。"""

        if item.state is None:
            raise TaskBoundaryError("task_not_active", "task payload 已清理")
        return TaskProjection(
            item.task_id, item.version, item.state, item.status, item.expires_at,
            claim_token=claim_token, context=item.context,
        )

    def _fact(self, item: _Checkpoint, action: str, reason: str, before: int | None) -> TaskLifecycleFact:
        """从 checkpoint 派生同源 lifecycle fact。"""

        return TaskLifecycleFact(self.safe_ref(item.task_id), action, reason, before, item.version, item.state.identity if item.state else None)

    def _now(self) -> datetime:
        """读取 timezone-aware 时钟，避免 TTL 比较歧义。"""

        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("task boundary clock 必须带 timezone")
        return value
