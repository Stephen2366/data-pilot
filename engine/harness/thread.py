"""M36/M37 进程内 clarification/follow-up checkpoint 与最小 Context Builder。

方案 A 的核心不是“用字典记聊天”，而是把一个未完成任务做成有 owner、版本、过期时间和
单调状态迁移的待办卡。外部只调用 create/resume/resolve/clear；锁、校验顺序和 Context
合并都藏在这个深 module 内，API 不能直接读写内部容器。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import secrets
from threading import RLock
from typing import Callable, Literal, Mapping
from uuid import uuid4

from engine.governance import TrustedCaller
from engine.harness.contracts import (
    AgentRunResult,
    ClarificationFieldSpec,
    ClarificationSpec,
    FollowUpActionSpec,
    FollowUpExecutionContext,
    FollowUpSpec,
    HarnessRequest,
    KnowledgeRuntimeKind,
)
from engine.rag.evidence import EvidenceRef
from engine.rag.answer_flow import AnswerEvidenceRequirement

THREAD_STATE_VERSION = "m37-thread-v2"
DEFAULT_THREAD_TTL_SECONDS = 900

ThreadStatus = Literal["pending", "claimed", "follow_up_ready", "follow_up_claimed", "resolved", "cleared"]
ThreadAction = Literal["created", "resumed", "follow_up_created", "follow_up_claimed", "resolved", "cleared", "rejected"]
ThreadSafety = Literal["passed", "blocked"]

THREAD_REASON_CODES = frozenset(
    {
        "clarification_pending",
        "clarification_resumed",
        "clarification_answers_invalid",
        "conversation_unavailable",
        "thread_expired",
        "thread_cleared",
        "thread_already_resumed",
        "thread_version_conflict",
        "thread_context_mismatch",
        "thread_checkpoint_failed",
        "state_version_incompatible",
        "budget_exhausted",
        "follow_up_ready",
        "follow_up_claimed",
        "follow_up_invalid",
        "follow_up_not_available",
        "follow_up_budget_exhausted",
        "follow_up_snapshot_invalid",
    }
)


class ThreadLifecycleError(ValueError):
    """安全、稳定的 thread lifecycle 失败；异常原文永不直接进入公开响应。"""

    def __init__(self, reason_code: str, message: str, *, safety_status: ThreadSafety = "passed") -> None:
        if reason_code not in THREAD_REASON_CODES:
            raise ValueError(f"未登记的 thread reason: {reason_code}")
        self.reason_code = reason_code
        self.safety_status = safety_status
        super().__init__(message)


@dataclass(frozen=True)
class PendingTask:
    """checkpoint 真正需要保存的任务事实，不保存 caller 对象、Evidence 或完整消息历史。"""

    original_question: str
    active_sql_role: str
    force_new_pipeline: bool
    schema_retrieval_profile: str
    schema_fusion_strategy: str
    clarification_spec: ClarificationSpec
    enable_bounded_follow_up: bool = False


@dataclass(frozen=True)
class FollowUpTask:
    """成功回答的最小任务/Evidence 快照；明确排除旧答案、rows、正文和 citation。"""

    original_question: str
    active_sql_role: str
    force_new_pipeline: bool
    schema_retrieval_profile: str
    schema_fusion_strategy: str
    route: Literal["sql", "rag"]
    evidence_refs: tuple[EvidenceRef, ...]
    requirement: AnswerEvidenceRequirement | None
    knowledge_runtime_kind: KnowledgeRuntimeKind
    follow_up_spec: FollowUpSpec


@dataclass(frozen=True)
class PendingThreadCheckpoint:
    """进程内不可变 checkpoint；每次迁移都以 replace 生成新版本。"""

    thread_id: str
    owner_ref: str
    state_version: str
    version: int
    status: ThreadStatus
    task: PendingTask | FollowUpTask
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    resume_count: int = 0
    context_ref: str | None = None


@dataclass(frozen=True)
class ThreadProjection:
    """AgentResponse 可公开的 thread 视图；只有合法 owner 才能取得 raw thread_id。"""

    thread_id: str
    checkpoint_version: int
    state_version: str
    status: ThreadStatus
    expires_at: datetime
    clarification: dict[str, object] | None = None
    follow_up: dict[str, object] | None = None
    follow_up_budget_remaining: int = 0

    def as_dict(self) -> dict[str, object]:
        """转换为 Pydantic/Trace 都能消费的 JSON-safe 字典。"""

        return {
            "thread_id": self.thread_id,
            "checkpoint_version": self.checkpoint_version,
            "state_version": self.state_version,
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "clarification": self.clarification,
            "follow_up": self.follow_up,
            "follow_up_budget_remaining": self.follow_up_budget_remaining,
        }


@dataclass(frozen=True)
class ThreadLifecycleFact:
    """Trace/Eval 使用的安全生命周期事实，不含 raw thread_id、问题或 answer value。"""

    thread_safe_ref: str
    action: ThreadAction
    reason_code: str
    version_before: int | None
    version_after: int | None
    state_version: str
    resume_count: int
    expires_at: datetime | None
    context_ref: str | None = None
    follow_up_budget_remaining: int = 0

    def safe_projection(self) -> dict[str, object]:
        """形成长期 Trace 白名单投影。"""

        return {
            "thread_safe_ref": self.thread_safe_ref,
            "action": self.action,
            "reason_code": self.reason_code,
            "version_before": self.version_before,
            "version_after": self.version_after,
            "state_version": self.state_version,
            "resume_count": self.resume_count,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "context_ref": self.context_ref,
            "follow_up_budget_remaining": self.follow_up_budget_remaining,
        }


@dataclass(frozen=True)
class ResumeClaim:
    """原子 claim 的输出：当前 HarnessRequest 与安全 lifecycle fact 一起交付。"""

    request: HarnessRequest
    projection: ThreadProjection
    lifecycle: ThreadLifecycleFact


@dataclass(frozen=True)
class FollowUpClaim:
    """一次 follow-up 原子 claim 的闭合输出。"""

    request: HarnessRequest
    projection: ThreadProjection
    lifecycle: ThreadLifecycleFact


_SQL_FOLLOW_UP = FollowUpSpec(
    identity="follow-up-sql-scope-v1",
    actions=(
        FollowUpActionSpec(
            action="adjust_sql_scope",
            label="调整统计范围",
            fields=(
                ClarificationFieldSpec("time_range", "时间范围", "time_range", max_length=80),
                ClarificationFieldSpec(
                    "group_by", "分组维度", "enum", allowed_values=("渠道", "商品", "退款原因"), max_length=20
                ),
            ),
            requirement_equivalent=False,
        ),
    ),
)

_RAG_FOLLOW_UP = FollowUpSpec(
    identity="follow-up-rag-evidence-v1",
    actions=(
        FollowUpActionSpec(
            action="explain_same_evidence",
            label="换一种方式解释同一规则",
            fields=(
                ClarificationFieldSpec(
                    "style", "解释方式", "enum", allowed_values=("通俗说明", "分步说明"), max_length=20
                ),
            ),
            requirement_equivalent=True,
        ),
        FollowUpActionSpec(
            action="ask_related_evidence",
            label="询问需要新证据的相关规则",
            fields=(ClarificationFieldSpec("detail", "具体问题", "text", max_length=80),),
            requirement_equivalent=False,
        ),
    ),
)

_FOLLOW_UP_CONTROL_TOKENS = (
    "忽略之前",
    "忽略系统",
    "system prompt",
    "调用tool",
    "调用 tool",
    "改走sql",
    "改走 sql",
    "route=",
    "<tool_call",
)


class ClarificationContextBuilder:
    """把 closed-world answers 变成当前任务，不接触完整 checkpoint store。"""

    def build(self, checkpoint: PendingThreadCheckpoint, answers: Mapping[str, str]) -> tuple[str, str]:
        """校验字段并生成 deterministic current task 与不可逆 context ref。

        非法输入在 checkpoint 被 claim 之前抛错，所以用户修正字段后仍可使用同一 version；
        这与“已经开始执行后失败不可重放”是两种不同语义。
        """

        spec = checkpoint.task.clarification_spec
        expected_keys = {field.key for field in spec.fields}
        actual_keys = set(answers)
        if actual_keys != expected_keys:
            raise ThreadLifecycleError("clarification_answers_invalid", "clarification answers 字段不闭合")

        normalized: dict[str, str] = {}
        for field in spec.fields:
            raw = answers[field.key]
            if not isinstance(raw, str):
                raise ThreadLifecycleError("clarification_answers_invalid", "clarification answer 必须是字符串")
            value = " ".join(raw.split())
            if not value or len(value) > field.max_length:
                raise ThreadLifecycleError("clarification_answers_invalid", "clarification answer 为空或过长")
            if field.value_type == "enum" and value not in field.allowed_values:
                raise ThreadLifecycleError("clarification_answers_invalid", "clarification enum 不在允许集合")
            normalized[field.key] = value

        # ★ 这里故意只有两个模板：M36 验证“结构化补条件后恢复”，不偷偷建设通用 query rewrite。
        if spec.context_template == "subject":
            current_question = f"关于{normalized['subject']}，应该如何处理？"
        elif spec.context_template == "analytics_scope":
            original = checkpoint.task.original_question.rstrip("?？。 ")
            current_question = (
                f"查询{original}，时间范围为{normalized['time_range']}，按{normalized['group_by']}统计"
            )
        else:  # pragma: no cover - ClarificationSpec 已用 Literal 限制，保留 fail-closed 防御。
            raise ThreadLifecycleError("state_version_incompatible", "未知 clarification context template")

        context_payload = {
            "original_question": checkpoint.task.original_question,
            "answers": normalized,
            "spec_identity": spec.identity,
        }
        context_ref = "context:" + sha256(
            json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return current_question, context_ref


class ThreadCheckpointManager:
    """M36/M37 方案 A 的进程内 bounded checkpoint 深 module。

    单个 ``RLock`` 同时保护状态检查与 claim 写入，等价于一个很小的 compare-and-set。Graph
    执行在锁外发生：慢 Tool 不会阻塞其他 thread，但同一 version 已先标为 claimed，因而不会
    被第二个请求重复执行。
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = DEFAULT_THREAD_TTL_SECONDS,
        clock: Callable[[], datetime] | None = None,
        accepted_state_version: str = THREAD_STATE_VERSION,
        context_builder: ClarificationContextBuilder | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("thread checkpoint TTL 必须为正数")
        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._accepted_state_version = accepted_state_version
        self._context_builder = context_builder or ClarificationContextBuilder()
        self._checkpoints: dict[str, PendingThreadCheckpoint] = {}
        self._lock = RLock()

    @property
    def runtime_identity(self) -> dict[str, object]:
        """返回可写入 Trace/Eval 的解析后运行身份。"""

        return {
            "adapter": "inprocess-bounded-thread-v2",
            "state_version": self._accepted_state_version,
            "ttl_seconds": self._ttl_seconds,
        }

    def create_pending(self, request: HarnessRequest, spec: ClarificationSpec) -> tuple[ThreadProjection, ThreadLifecycleFact]:
        """为首次 clarification 创建版本 1 的 pending checkpoint。"""

        if request.caller is None or request.active_sql_role is None:
            raise ThreadLifecycleError("conversation_unavailable", "无可信 caller 不能创建 thread", safety_status="blocked")
        now = self._now()
        thread_id = uuid4().hex
        checkpoint = PendingThreadCheckpoint(
            thread_id=thread_id,
            owner_ref=self._owner_ref(request.caller),
            state_version=THREAD_STATE_VERSION,
            version=1,
            status="pending",
            task=PendingTask(
                original_question=request.question,
                active_sql_role=request.active_sql_role,
                force_new_pipeline=request.force_new_pipeline,
                schema_retrieval_profile=request.schema_retrieval_profile,
                schema_fusion_strategy=request.schema_fusion_strategy,
                clarification_spec=spec,
                enable_bounded_follow_up=request.enable_bounded_follow_up,
            ),
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        with self._lock:
            self._checkpoints[thread_id] = checkpoint
        return self._projection(checkpoint), self._fact(
            checkpoint, action="created", reason_code="clarification_pending", before=None
        )

    def claim_resume(
        self,
        *,
        thread_id: str,
        expected_version: int,
        caller: TrustedCaller | None,
        active_sql_role: str | None,
        answers: Mapping[str, str],
        run_id: str,
    ) -> ResumeClaim:
        """校验 owner/lifecycle/answers，并原子消费一个 pending version。"""

        if caller is None:
            raise ThreadLifecycleError("conversation_unavailable", "caller 不可信", safety_status="blocked")
        with self._lock:
            checkpoint = self._checkpoints.get(thread_id)
            # 步骤 1：missing 与 wrong owner 使用同一公开结果，thread id 不能充当授权凭证。========
            if checkpoint is None or not secrets.compare_digest(checkpoint.owner_ref, self._owner_ref(caller)):
                raise ThreadLifecycleError(
                    "conversation_unavailable", "thread 不存在或不属于当前 caller", safety_status="blocked"
                )

            # 步骤 2：只有 owner 通过后才报告它自己的 lifecycle 细节，避免跨 caller 探测。----------
            self._validate_resumable(checkpoint, expected_version=expected_version, active_sql_role=active_sql_role)
            current_question, context_ref = self._context_builder.build(checkpoint, answers)

            # 步骤 3：在释放锁、调用慢 Tool 前先 claim；另一个同 version 请求随后只能失败。----------
            claimed = replace(
                checkpoint,
                version=checkpoint.version + 1,
                status="claimed",
                updated_at=self._now(),
                resume_count=checkpoint.resume_count + 1,
                context_ref=context_ref,
            )
            self._checkpoints[thread_id] = claimed

        request = HarnessRequest(
            question=current_question,
            run_id=run_id,
            caller=caller,
            active_sql_role=checkpoint.task.active_sql_role,
            force_new_pipeline=checkpoint.task.force_new_pipeline,
            schema_retrieval_profile=checkpoint.task.schema_retrieval_profile,
            schema_fusion_strategy=checkpoint.task.schema_fusion_strategy,
            enable_bounded_follow_up=checkpoint.task.enable_bounded_follow_up,
        )
        return ResumeClaim(
            request=request,
            projection=self._projection(claimed),
            lifecycle=self._fact(
                claimed,
                action="resumed",
                reason_code="clarification_resumed",
                before=checkpoint.version,
            ),
        )

    def create_follow_up_ready(
        self,
        request: HarnessRequest,
        result: AgentRunResult,
    ) -> tuple[ThreadProjection, ThreadLifecycleFact]:
        """为显式 opt-in 的成功 turn 建立一张最多消费一次的 follow-up 卡。"""

        task = self._follow_up_task(request, result)
        if request.caller is None:
            raise ThreadLifecycleError("conversation_unavailable", "无可信 caller", safety_status="blocked")
        now = self._now()
        checkpoint = PendingThreadCheckpoint(
            thread_id=uuid4().hex,
            owner_ref=self._owner_ref(request.caller),
            state_version=THREAD_STATE_VERSION,
            version=1,
            status="follow_up_ready",
            task=task,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
        )
        with self._lock:
            self._checkpoints[checkpoint.thread_id] = checkpoint
        return self._projection(checkpoint), self._fact(
            checkpoint, action="follow_up_created", reason_code="follow_up_ready", before=None
        )

    def promote_claimed_to_follow_up(
        self,
        thread_id: str,
        *,
        claimed_version: int,
        request: HarnessRequest,
        result: AgentRunResult,
    ) -> tuple[ThreadProjection, ThreadLifecycleFact]:
        """clarification 成功后在同一 owner/version 链上进入 follow-up-ready。"""

        task = self._follow_up_task(request, result)
        with self._lock:
            checkpoint = self._checkpoints.get(thread_id)
            if checkpoint is None or checkpoint.status != "claimed" or checkpoint.version != claimed_version:
                raise ThreadLifecycleError("thread_version_conflict", "无法推进非当前 claimed checkpoint")
            ready = replace(
                checkpoint,
                version=checkpoint.version + 1,
                status="follow_up_ready",
                task=task,
                updated_at=self._now(),
            )
            self._checkpoints[thread_id] = ready
        return self._projection(ready), self._fact(
            ready, action="follow_up_created", reason_code="follow_up_ready", before=checkpoint.version
        )

    def claim_follow_up(
        self,
        *,
        thread_id: str,
        expected_version: int,
        caller: TrustedCaller | None,
        active_sql_role: str | None,
        action: str,
        fields: Mapping[str, str],
        run_id: str,
    ) -> FollowUpClaim:
        """先校验 closed-world delta，再以 compare-and-set 消费唯一 follow-up 预算。"""

        if caller is None:
            raise ThreadLifecycleError("conversation_unavailable", "caller 不可信", safety_status="blocked")
        with self._lock:
            checkpoint = self._checkpoints.get(thread_id)
            if checkpoint is None or not secrets.compare_digest(checkpoint.owner_ref, self._owner_ref(caller)):
                raise ThreadLifecycleError(
                    "conversation_unavailable", "thread 不存在或不属于当前 caller", safety_status="blocked"
                )
            self._validate_follow_up_claim(
                checkpoint, expected_version=expected_version, active_sql_role=active_sql_role
            )
            task = checkpoint.task
            if not isinstance(task, FollowUpTask):
                raise ThreadLifecycleError("state_version_incompatible", "follow-up task 类型不兼容")
            action_spec = next((item for item in task.follow_up_spec.actions if item.action == action), None)
            if action_spec is None:
                raise ThreadLifecycleError("follow_up_invalid", "action 不在服务端签发集合")
            normalized = self._validated_fields(action_spec.fields, fields, reason_code="follow_up_invalid")
            question = self._follow_up_question(task, action_spec, normalized)
            context_ref = "context:" + sha256(
                json.dumps(
                    {"previous_route": task.route, "action": action, "fields": normalized},
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            claimed = replace(
                checkpoint,
                version=checkpoint.version + 1,
                status="follow_up_claimed",
                updated_at=self._now(),
                resume_count=checkpoint.resume_count + 1,
                context_ref=context_ref,
            )
            self._checkpoints[thread_id] = claimed

        follow_up_context = FollowUpExecutionContext(
            action=action,
            previous_route=task.route,
            requirement_equivalent=action_spec.requirement_equivalent,
            previous_requirement=task.requirement,
            current_requirement=(
                task.requirement
                if action_spec.requirement_equivalent
                else AnswerEvidenceRequirement(max_claims=1)
                if task.route == "rag"
                else None
            ),
            old_evidence_refs=task.evidence_refs,
            knowledge_runtime_kind=task.knowledge_runtime_kind,
        )
        request = HarnessRequest(
            question=question,
            run_id=run_id,
            caller=caller,
            active_sql_role=task.active_sql_role,
            force_new_pipeline=task.force_new_pipeline,
            schema_retrieval_profile=task.schema_retrieval_profile,
            schema_fusion_strategy=task.schema_fusion_strategy,
            follow_up_context=follow_up_context,
        )
        return FollowUpClaim(
            request=request,
            projection=self._projection(claimed),
            lifecycle=self._fact(
                claimed, action="follow_up_claimed", reason_code="follow_up_claimed", before=checkpoint.version
            ),
        )

    def resolve(self, thread_id: str, *, claimed_version: int) -> tuple[ThreadProjection, ThreadLifecycleFact]:
        """Graph 结束后把已 claim checkpoint 单调推进为 resolved。"""

        with self._lock:
            checkpoint = self._checkpoints.get(thread_id)
            if checkpoint is None or checkpoint.status not in {"claimed", "follow_up_claimed"} or checkpoint.version != claimed_version:
                raise ThreadLifecycleError("thread_version_conflict", "无法 resolve 非当前 claimed checkpoint")
            was_follow_up = checkpoint.status == "follow_up_claimed"
            resolved = replace(
                checkpoint,
                version=checkpoint.version + 1,
                status="resolved",
                updated_at=self._now(),
            )
            self._checkpoints[thread_id] = resolved
        return self._projection(resolved), self._fact(
            resolved,
            action="resolved",
            reason_code="follow_up_claimed" if was_follow_up else "clarification_resumed",
            before=checkpoint.version,
        )

    def clear(
        self,
        *,
        thread_id: str,
        expected_version: int,
        caller: TrustedCaller | None,
    ) -> tuple[ThreadProjection, ThreadLifecycleFact]:
        """由合法 owner 显式清理 checkpoint；保留短期 tombstone 阻止旧请求重放。"""

        if caller is None:
            raise ThreadLifecycleError("conversation_unavailable", "caller 不可信", safety_status="blocked")
        with self._lock:
            checkpoint = self._checkpoints.get(thread_id)
            if checkpoint is None or not secrets.compare_digest(checkpoint.owner_ref, self._owner_ref(caller)):
                raise ThreadLifecycleError(
                    "conversation_unavailable", "thread 不存在或不属于当前 caller", safety_status="blocked"
                )
            if checkpoint.version != expected_version:
                raise ThreadLifecycleError("thread_version_conflict", "checkpoint version 已变化")
            if checkpoint.status == "cleared":
                raise ThreadLifecycleError("thread_cleared", "checkpoint 已清理")
            cleared = replace(
                checkpoint,
                version=checkpoint.version + 1,
                status="cleared",
                updated_at=self._now(),
            )
            self._checkpoints[thread_id] = cleared
        return self._projection(cleared), self._fact(
            cleared, action="cleared", reason_code="thread_cleared", before=checkpoint.version
        )

    def lifecycle_rejection(self, *, thread_id: str, error: ThreadLifecycleError) -> ThreadLifecycleFact:
        """为前置失败生成不泄露 raw thread id 的统一 Trace/Eval 事实。"""

        return ThreadLifecycleFact(
            thread_safe_ref=self._thread_safe_ref(thread_id),
            action="rejected",
            reason_code=error.reason_code,
            version_before=None,
            version_after=None,
            state_version=self._accepted_state_version,
            resume_count=0,
            expires_at=None,
            follow_up_budget_remaining=0,
        )

    def _validate_resumable(
        self,
        checkpoint: PendingThreadCheckpoint,
        *,
        expected_version: int,
        active_sql_role: str | None,
    ) -> None:
        """按不会产生跨 owner 侧信道的顺序检查 lifecycle。"""

        if checkpoint.state_version != self._accepted_state_version:
            raise ThreadLifecycleError("state_version_incompatible", "checkpoint state version 不兼容")
        if checkpoint.status == "cleared":
            raise ThreadLifecycleError("thread_cleared", "checkpoint 已清理")
        if checkpoint.status != "pending":
            raise ThreadLifecycleError("thread_already_resumed", "checkpoint 已被消费")
        if self._now() >= checkpoint.expires_at:
            raise ThreadLifecycleError("thread_expired", "checkpoint 已过期")
        if checkpoint.version != expected_version:
            raise ThreadLifecycleError("thread_version_conflict", "checkpoint version 已变化")
        if active_sql_role != checkpoint.task.active_sql_role:
            raise ThreadLifecycleError("thread_context_mismatch", "active role 与 pending task 不一致", safety_status="blocked")

    def _validate_follow_up_claim(
        self,
        checkpoint: PendingThreadCheckpoint,
        *,
        expected_version: int,
        active_sql_role: str | None,
    ) -> None:
        """按 M36 相同 owner/version/TTL 顺序检查 follow-up-ready。"""

        if checkpoint.state_version != self._accepted_state_version:
            raise ThreadLifecycleError("state_version_incompatible", "checkpoint state version 不兼容")
        if checkpoint.status == "cleared":
            raise ThreadLifecycleError("thread_cleared", "checkpoint 已清理")
        if checkpoint.status in {"follow_up_claimed", "resolved", "claimed"}:
            raise ThreadLifecycleError("follow_up_budget_exhausted", "follow-up 已消费")
        if checkpoint.status != "follow_up_ready":
            raise ThreadLifecycleError("follow_up_not_available", "当前 thread 不能追问")
        if self._now() >= checkpoint.expires_at:
            raise ThreadLifecycleError("thread_expired", "checkpoint 已过期")
        if checkpoint.version != expected_version:
            raise ThreadLifecycleError("thread_version_conflict", "checkpoint version 已变化")
        task = checkpoint.task
        if not isinstance(task, FollowUpTask) or active_sql_role != task.active_sql_role:
            raise ThreadLifecycleError("thread_context_mismatch", "active role 与 follow-up task 不一致", safety_status="blocked")

    @staticmethod
    def _validated_fields(
        specs: tuple[ClarificationFieldSpec, ...],
        values: Mapping[str, str],
        *,
        reason_code: str,
    ) -> dict[str, str]:
        """复用 clarification 的字段纪律，但保留独立稳定 reason。"""

        if set(values) != {field.key for field in specs}:
            raise ThreadLifecycleError(reason_code, "follow-up fields 不闭合")
        normalized: dict[str, str] = {}
        for field in specs:
            raw = values[field.key]
            if not isinstance(raw, str):
                raise ThreadLifecycleError(reason_code, "follow-up field 必须是字符串")
            value = " ".join(raw.split())
            if not value or len(value) > field.max_length:
                raise ThreadLifecycleError(reason_code, "follow-up field 为空或过长")
            if field.value_type == "enum" and value not in field.allowed_values:
                raise ThreadLifecycleError(reason_code, "follow-up enum 不在允许集合")
            lowered = value.lower().replace("　", " ")
            if any(token in lowered for token in _FOLLOW_UP_CONTROL_TOKENS):
                raise ThreadLifecycleError(reason_code, "follow-up field 包含控制指令")
            normalized[field.key] = value
        return normalized

    @staticmethod
    def _follow_up_question(
        task: FollowUpTask,
        action: FollowUpActionSpec,
        fields: Mapping[str, str],
    ) -> str:
        """只用三个固定模板形成 current task，不执行自由文本 query rewrite。"""

        original = task.original_question.rstrip("?？。 ")
        if action.action == "adjust_sql_scope":
            return f"查询{original}，时间范围为{fields['time_range']}，按{fields['group_by']}统计"
        if action.action == "explain_same_evidence":
            return f"请用{fields['style']}解释同一条规则：{original}"
        if action.action == "ask_related_evidence":
            return f"围绕原任务“{original}”，关于{fields['detail']}请说明相关规则。"
        raise ThreadLifecycleError("follow_up_invalid", "未知 follow-up action")

    @staticmethod
    def _follow_up_task(request: HarnessRequest, result: AgentRunResult) -> FollowUpTask:
        """从唯一成功结果建立不含业务内容的快照；任何缺口都失败关闭。"""

        observation = result.observation
        if (
            not request.enable_bounded_follow_up
            or request.caller is None
            or request.active_sql_role is None
            or result.route not in {"sql", "rag"}
            or result.execution_status != "completed"
            or result.answer_status != "complete"
            or result.safety_status != "passed"
            or observation is None
            or not observation.evidence_refs
        ):
            raise ThreadLifecycleError("follow_up_snapshot_invalid", "结果不具备 follow-up 快照资格")
        try:
            refs = tuple(EvidenceRef(**item) for item in observation.evidence_refs)
        except (TypeError, ValueError) as exc:
            raise ThreadLifecycleError("follow_up_snapshot_invalid", "EvidenceRef 投影不闭合") from exc
        runtime_kind: KnowledgeRuntimeKind = "not_applicable"
        spec = _SQL_FOLLOW_UP
        requirement = None
        if result.route == "rag":
            raw_kind = observation.diagnostics.get("knowledge_runtime_kind", "business_release")
            if raw_kind not in {"business_release", "external_profile"}:
                raise ThreadLifecycleError("follow_up_snapshot_invalid", "knowledge runtime kind 未登记")
            runtime_kind = raw_kind
            spec = _RAG_FOLLOW_UP
            requirement = result.route_decision.requirement
            if requirement is None:
                raise ThreadLifecycleError("follow_up_snapshot_invalid", "RAG requirement 缺失")
        return FollowUpTask(
            original_question=request.question,
            active_sql_role=request.active_sql_role,
            force_new_pipeline=request.force_new_pipeline,
            schema_retrieval_profile=request.schema_retrieval_profile,
            schema_fusion_strategy=request.schema_fusion_strategy,
            route=result.route,
            evidence_refs=refs,
            requirement=requirement,
            knowledge_runtime_kind=runtime_kind,
            follow_up_spec=spec,
        )

    def _projection(self, checkpoint: PendingThreadCheckpoint) -> ThreadProjection:
        """仅向合法 caller 返回 raw id；resolved/cleared 不再暴露待补字段。"""

        clarification = (
            checkpoint.task.clarification_spec.safe_projection()
            if checkpoint.status == "pending" and isinstance(checkpoint.task, PendingTask)
            else None
        )
        follow_up = (
            checkpoint.task.follow_up_spec.safe_projection()
            if checkpoint.status == "follow_up_ready" and isinstance(checkpoint.task, FollowUpTask)
            else None
        )
        return ThreadProjection(
            thread_id=checkpoint.thread_id,
            checkpoint_version=checkpoint.version,
            state_version=checkpoint.state_version,
            status=checkpoint.status,
            expires_at=checkpoint.expires_at,
            clarification=clarification,
            follow_up=follow_up,
            follow_up_budget_remaining=1 if checkpoint.status == "follow_up_ready" else 0,
        )

    def _fact(
        self,
        checkpoint: PendingThreadCheckpoint,
        *,
        action: ThreadAction,
        reason_code: str,
        before: int | None,
    ) -> ThreadLifecycleFact:
        """从同一 checkpoint 派生 Trace/Eval 事实，避免调用者自行猜 version。"""

        return ThreadLifecycleFact(
            thread_safe_ref=self._thread_safe_ref(checkpoint.thread_id),
            action=action,
            reason_code=reason_code,
            version_before=before,
            version_after=checkpoint.version,
            state_version=checkpoint.state_version,
            resume_count=checkpoint.resume_count,
            expires_at=checkpoint.expires_at,
            context_ref=checkpoint.context_ref,
            follow_up_budget_remaining=1 if checkpoint.status == "follow_up_ready" else 0,
        )

    def _now(self) -> datetime:
        """取得 timezone-aware 当前时间，拒绝会让过期比较歧义的 naive datetime。"""

        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("thread checkpoint clock 必须返回 timezone-aware datetime")
        return value

    @staticmethod
    def _owner_ref(caller: TrustedCaller) -> str:
        """把已解析 owner 与 tenant 绑定为内部比较值。

        ``audit_ref`` 刻意不含 tenant，适合跨租户审计聚合，却不能单独充当 checkpoint owner。
        显式 ``thread_owner_ref`` 由认证适配器负责租户作用域；没有它时必须把 tenant 一起哈希。
        """

        owner_identity = caller.thread_owner_ref or f"{caller.audit_ref}\0tenant:{caller.tenant_id or '-'}"
        return sha256(owner_identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _thread_safe_ref(thread_id: str) -> str:
        """Trace 只保存不可逆 ref，防止日志中的 raw id 被拿去尝试恢复。"""

        return "thread:" + sha256(thread_id.encode("utf-8")).hexdigest()
