"""M43-C：TaskState 的进程内安全边界。

这是可替换 adapter seam，不冒充 durable checkpoint。owner、TTL、version 与 claim/commit
都在锁内检查；未知 task 和错误 owner 统一返回 ``task_unavailable``。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from threading import RLock
from typing import Callable, Literal
from uuid import uuid4

from engine.governance import TrustedCaller
from engine.phase4b.task_runtime import TaskState


class TaskBoundaryError(ValueError):
    """Task lifecycle 的稳定失败；reason/safety 可直接投影为安全拒绝。"""

    def __init__(self, reason_code: str, message: str, *, safety_status: Literal["passed", "blocked"] = "passed") -> None:
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

    def safe_projection(self) -> dict[str, object]:
        return {"task_id": self.task_id, "task_version": self.task_version, "state": self.state.safe_projection(), "status": self.status, "expires_at": self.expires_at.isoformat()}


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

    def safe_projection(self) -> dict[str, object]:
        return {"task_safe_ref": self.task_safe_ref, "action": self.action, "reason_code": self.reason_code, "version_before": self.version_before, "version_after": self.version_after, "state_identity": self.state_identity, "previous_task_safe_ref": self.previous_task_safe_ref}


@dataclass(frozen=True)
class _Checkpoint:
    """manager 私有存储形状；claimed 是一次执行权，不能由客户端构造。"""

    task_id: str
    owner_ref: str
    version: int
    status: Literal["claimed", "active", "cancelled", "switched", "cleared"]
    state: TaskState
    expires_at: datetime


class TaskBoundary:
    """封装完整 task 生命周期；endpoint 不接触内部字典或 owner 比较值。"""

    def __init__(self, *, ttl_seconds: int = 1800, clock: Callable[[], datetime] | None = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._items: dict[str, _Checkpoint] = {}
        self._lock = RLock()

    @property
    def runtime_identity(self) -> dict[str, object]:
        """明确宣告 process-local，防止 M43 被误报成 B5 durable state。"""

        return {"identity": "phase4b-in-memory-task-boundary-v1", "durability": "process_local_non_durable", "ttl_seconds": self._ttl_seconds, "atomic_claim_commit": True}

    def start(self, *, caller: TrustedCaller | None, state: TaskState) -> tuple[TaskProjection, TaskLifecycleFact]:
        """为可信 owner 签发一个 version=1 的新 task。"""

        owner = self.owner_ref(caller)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        now = self._now()
        item = _Checkpoint(uuid4().hex, owner, 1, "active", state, now + timedelta(seconds=self._ttl_seconds))
        with self._lock:
            self._items[item.task_id] = item
        return self._projection(item), self._fact(item, "started", "task_started", None)

    def claim(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None) -> TaskProjection:
        """以 owner/version/TTL compare-and-set 消费一次执行权。"""

        owner = self.owner_ref(caller)
        with self._lock:
            item = self._owned(task_id, owner)
            if item.status != "active":
                raise TaskBoundaryError("task_not_active", "task 已结束")
            if self._now() >= item.expires_at:
                raise TaskBoundaryError("task_expired", "task 已过期")
            if item.version != expected_version:
                raise TaskBoundaryError("task_version_conflict", "task version 已变化")
            claimed = replace(item, version=item.version + 1, status="claimed")
            self._items[task_id] = claimed
        return self._projection(claimed)

    def commit(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState, terminal_status: str | None = None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """只提交仍为当前版本的 claim；失败时绝不覆盖其他 turn。"""

        owner = self.owner_ref(caller)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        with self._lock:
            item = self._owned(claim.task_id, owner)
            if item.status != "claimed" or item.version != claim.task_version:
                raise TaskBoundaryError("task_version_conflict", "claim 已失效")
            status = terminal_status if terminal_status in {"cancelled", "switched", "cleared"} else "active"
            committed = replace(item, version=item.version + 1, status=status, state=state, expires_at=self._now() + timedelta(seconds=self._ttl_seconds))
            self._items[item.task_id] = committed
        return self._projection(committed), self._fact(committed, status, f"task_{status}", claim.task_version - 1)

    def clear(self, *, task_id: str, expected_version: int, caller: TrustedCaller | None) -> tuple[TaskProjection, TaskLifecycleFact]:
        """显式清理并使剩余 active Evidence 失效。"""

        claim = self.claim(task_id=task_id, expected_version=expected_version, caller=caller)
        evidence = tuple(
            replace(item, validity="invalidated", invalidation_reason="task_cleared")
            if item.validity == "active" else item
            for item in claim.state.evidence
        )
        state = replace(claim.state, status="cleared", termination="cleared_by_caller", evidence=evidence)
        return self.commit(claim=claim, caller=caller, state=state, terminal_status="cleared")

    def switch(self, *, claim: TaskProjection, caller: TrustedCaller | None, state: TaskState) -> tuple[TaskProjection, TaskLifecycleFact]:
        """在同一把锁内终止旧 task 并签发新 task，避免出现只完成半边的切换。"""

        owner = self.owner_ref(caller)
        if state.owner_ref != owner:
            raise TaskBoundaryError("task_owner_mismatch", "state owner 与 caller 不一致", safety_status="blocked")
        now = self._now()
        with self._lock:
            old = self._owned(claim.task_id, owner)
            if old.status != "claimed" or old.version != claim.task_version:
                raise TaskBoundaryError("task_version_conflict", "switch claim 已失效")
            retired_evidence = tuple(
                replace(item, validity="invalidated", invalidation_reason="task_switched")
                if item.validity == "active" else item
                for item in old.state.evidence
            )
            retired_state = replace(old.state, status="switched", termination="switched_by_caller", evidence=retired_evidence)
            self._items[old.task_id] = replace(old, version=old.version + 1, status="switched", state=retired_state)
            new = _Checkpoint(uuid4().hex, owner, 1, "active", state, now + timedelta(seconds=self._ttl_seconds))
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

    @staticmethod
    def safe_ref(task_id: str) -> str:
        """为 Trace/Eval 计算不可恢复的 task 引用。"""

        return "task:" + sha256(task_id.encode()).hexdigest()

    def _owned(self, task_id: str, owner: str) -> _Checkpoint:
        """统一未知/错 owner 失败，避免 task 枚举侧信道。"""

        item = self._items.get(task_id)
        if item is None or not secrets.compare_digest(item.owner_ref, owner):
            raise TaskBoundaryError("task_unavailable", "task 不存在或不属于 caller", safety_status="blocked")
        return item

    def _projection(self, item: _Checkpoint) -> TaskProjection:
        """把私有 checkpoint 收窄为 owner 可见投影。"""

        return TaskProjection(item.task_id, item.version, item.state, item.status, item.expires_at)

    def _fact(self, item: _Checkpoint, action: str, reason: str, before: int | None) -> TaskLifecycleFact:
        """从 checkpoint 派生同源 lifecycle fact。"""

        return TaskLifecycleFact(self.safe_ref(item.task_id), action, reason, before, item.version, item.state.identity)

    def _now(self) -> datetime:
        """读取 timezone-aware 时钟，避免 TTL 比较歧义。"""

        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("task boundary clock 必须带 timezone")
        return value
