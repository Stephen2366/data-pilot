"""M36 turn-level Harness seam：统一单轮、pending、resume 与 lifecycle 拒绝。

API 只调用 ``run_turn``，不直接创建 checkpoint、合并问题或拼四轴。这样 M35 的 compiled
Graph 仍是业务 route/Tool/controller，而 M36 只在它外面增加一次 pre-Tool clarification
lifecycle；两层不会各自生成业务答案。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Mapping

from engine.harness.contracts import AgentRunResult, HarnessRequest, RouteDecision
from engine.harness.graph import HarnessRuntime, run_harness
from engine.governance import TrustedCaller
from engine.harness.thread import (
    ThreadCheckpointManager,
    ThreadLifecycleError,
    ThreadLifecycleFact,
    ThreadProjection,
)

TurnAction = Literal["initial", "resume", "rejected"]


@dataclass(frozen=True)
class TurnRequest:
    """一个 HTTP turn 投影后的最小输入；resume 三字段必须同时出现。"""

    harness_request: HarnessRequest
    thread_id: str | None = None
    expected_version: int | None = None
    clarification_answers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """区分 initial/resume 并拒绝缺字段的半截恢复请求。"""

        is_resume = self.thread_id is not None
        if is_resume != (self.expected_version is not None):
            raise ValueError("thread_id 与 expected_version 必须同时提供")
        if is_resume != bool(self.clarification_answers):
            raise ValueError("resume 必须提供 clarification_answers；initial turn 不得提供")
        if self.expected_version is not None and self.expected_version <= 0:
            raise ValueError("expected_version 必须为正数")


@dataclass(frozen=True)
class AgentTurnResult:
    """API/Trace/Eval 共用的唯一 turn 事实。"""

    result: AgentRunResult
    turn_action: TurnAction
    graph_invocation_count: int
    thread: ThreadProjection | None = None
    lifecycle: ThreadLifecycleFact | None = None
    checkpoint_runtime: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """把 accepted/rejected 与 Graph 次数绑定为不可矛盾的事实。"""

        expected = 0 if self.turn_action == "rejected" else 1
        if self.graph_invocation_count != expected:
            raise ValueError("accepted turn 必须一次 Graph；lifecycle rejected 必须零次 Graph")


@dataclass(frozen=True)
class ThreadControlResult:
    """显式 clear 的闭合结果；它不调用 Graph，也不生成业务答案。"""

    ok: bool
    reason_code: str
    safety_status: Literal["passed", "blocked"]
    message: str
    thread: ThreadProjection | None
    lifecycle: ThreadLifecycleFact


def run_turn(
    *,
    request: TurnRequest,
    runtime: HarnessRuntime,
    checkpoint_manager: ThreadCheckpointManager,
) -> AgentTurnResult:
    """★ 运行 initial 或一次 resume，并把所有路径收敛为 AgentTurnResult。"""

    if request.thread_id is None:
        return _run_initial(request.harness_request, runtime=runtime, checkpoint_manager=checkpoint_manager)
    return _run_resume(request, runtime=runtime, checkpoint_manager=checkpoint_manager)


def clear_thread(
    *,
    thread_id: str,
    expected_version: int,
    caller: TrustedCaller | None,
    checkpoint_manager: ThreadCheckpointManager,
) -> ThreadControlResult:
    """由应用层调用 manager 的安全 clear interface，错误时不回显 checkpoint。"""

    try:
        projection, lifecycle = checkpoint_manager.clear(
            thread_id=thread_id,
            expected_version=expected_version,
            caller=caller,
        )
        return ThreadControlResult(
            ok=True,
            reason_code="thread_cleared",
            safety_status="passed",
            message="当前待补任务已清理。",
            thread=projection,
            lifecycle=lifecycle,
        )
    except ThreadLifecycleError as exc:
        return ThreadControlResult(
            ok=False,
            reason_code=exc.reason_code,
            safety_status=exc.safety_status,
            message=_public_message(exc.reason_code),
            thread=None,
            lifecycle=checkpoint_manager.lifecycle_rejection(thread_id=thread_id, error=exc),
        )


def _run_initial(
    request: HarnessRequest,
    *,
    runtime: HarnessRuntime,
    checkpoint_manager: ThreadCheckpointManager,
) -> AgentTurnResult:
    """单次执行 M35 Graph；只有闭合 clarification 才创建 pending checkpoint。"""

    result = run_harness(request=request, runtime=runtime)
    if result.answer_status != "clarification_required":
        return AgentTurnResult(
            result=result,
            turn_action="initial",
            graph_invocation_count=1,
            checkpoint_runtime=checkpoint_manager.runtime_identity,
        )

    spec = result.route_decision.clarification_spec
    if spec is None:  # RouteDecision 自身会拒绝该状态；保留防御以防未来反序列化绕过 dataclass。
        return AgentTurnResult(
            result=_lifecycle_failure_result(
                reason_code="thread_checkpoint_failed",
                safety_status="passed",
                caller_safe_ref=result.caller_safe_ref,
                graph_steps=result.graph_steps,
            ),
            turn_action="initial",
            graph_invocation_count=1,
            checkpoint_runtime=checkpoint_manager.runtime_identity,
        )
    try:
        projection, lifecycle = checkpoint_manager.create_pending(request, spec)
    except ThreadLifecycleError:
        return AgentTurnResult(
            result=_lifecycle_failure_result(
                reason_code="thread_checkpoint_failed",
                safety_status="passed",
                caller_safe_ref=result.caller_safe_ref,
                graph_steps=result.graph_steps,
            ),
            turn_action="initial",
            graph_invocation_count=1,
            checkpoint_runtime=checkpoint_manager.runtime_identity,
        )
    return AgentTurnResult(
        result=result,
        turn_action="initial",
        graph_invocation_count=1,
        thread=projection,
        lifecycle=lifecycle,
        checkpoint_runtime=checkpoint_manager.runtime_identity,
    )


def _run_resume(
    request: TurnRequest,
    *,
    runtime: HarnessRuntime,
    checkpoint_manager: ThreadCheckpointManager,
) -> AgentTurnResult:
    """先原子 claim，再在锁外执行一次 Graph，最后无条件 resolve 为不可重放状态。"""

    harness_request = request.harness_request
    thread_id = request.thread_id or ""
    try:
        claim = checkpoint_manager.claim_resume(
            thread_id=thread_id,
            expected_version=request.expected_version or 0,
            caller=harness_request.caller,
            active_sql_role=harness_request.active_sql_role,
            answers=request.clarification_answers,
            run_id=harness_request.run_id,
        )
    except ThreadLifecycleError as exc:
        return AgentTurnResult(
            result=_lifecycle_failure_result(
                reason_code=exc.reason_code,
                safety_status=exc.safety_status,
                caller_safe_ref=harness_request.caller.audit_ref if harness_request.caller else None,
            ),
            turn_action="rejected",
            graph_invocation_count=0,
            lifecycle=checkpoint_manager.lifecycle_rejection(thread_id=thread_id, error=exc),
            checkpoint_runtime=checkpoint_manager.runtime_identity,
        )

    # ★ claim 已经消耗执行权。即使 Graph/resolve 出错也不能退回 pending，否则重复请求会二次调用 Tool。
    result = run_harness(request=claim.request, runtime=runtime)
    if result.answer_status == "clarification_required":
        result = _budget_exhausted_result(result)
    try:
        projection, lifecycle = checkpoint_manager.resolve(
            thread_id,
            claimed_version=claim.projection.checkpoint_version,
        )
        # 一个 resume turn 对外记录 pending version → resolved version，内部 claimed 版本不让
        # 调用者拼接；这样 Trace 可以直接证明整个 turn 只消费了一次执行权。
        lifecycle = replace(lifecycle, version_before=claim.lifecycle.version_before)
    except ThreadLifecycleError:
        # Tool 可能已经执行成功，不能重跑；只把本 turn 收敛为 checkpoint failure。
        result = _lifecycle_failure_result(
            reason_code="thread_checkpoint_failed",
            safety_status="passed",
            caller_safe_ref=result.caller_safe_ref,
            graph_steps=result.graph_steps,
        )
        projection, lifecycle = claim.projection, claim.lifecycle
    return AgentTurnResult(
        result=result,
        turn_action="resume",
        graph_invocation_count=1,
        thread=projection,
        lifecycle=lifecycle,
        checkpoint_runtime=checkpoint_manager.runtime_identity,
    )


def _budget_exhausted_result(previous: AgentRunResult) -> AgentRunResult:
    """一次 resume 后仍不清楚时停止，不创建嵌套 pending checkpoint。"""

    decision = RouteDecision("none", "budget_exhausted", False, "failed", decision_source="controller")
    return AgentRunResult(
        route="none",
        execution_status="failed",
        answer_status="no_answer",
        safety_status="passed",
        reason_code="budget_exhausted",
        answer=_public_message("budget_exhausted"),
        route_decision=decision,
        observation=None,
        termination_action="failed",
        graph_steps=(*previous.graph_steps, "resume_budget_stop"),
        caller_safe_ref=previous.caller_safe_ref,
    )


def _lifecycle_failure_result(
    *,
    reason_code: str,
    safety_status: Literal["passed", "blocked"],
    caller_safe_ref: str | None,
    graph_steps: tuple[str, ...] = (),
) -> AgentRunResult:
    """前置 lifecycle 拒绝也从 Harness seam 生成四轴，API 不自行判断。"""

    termination = "blocked" if safety_status == "blocked" else "failed"
    decision = RouteDecision("none", reason_code, False, termination, decision_source="controller")
    return AgentRunResult(
        route="none",
        execution_status="not_started" if safety_status == "blocked" else "failed",
        answer_status="no_answer",
        safety_status=safety_status,
        reason_code=reason_code,
        answer=_public_message(reason_code),
        route_decision=decision,
        observation=None,
        termination_action=termination,
        graph_steps=(*graph_steps, "thread_lifecycle_rejected"),
        caller_safe_ref=caller_safe_ref,
    )


def _public_message(reason_code: str) -> str:
    """稳定 reason 到安全文案的单向映射；不回显异常或 checkpoint 内容。"""

    messages = {
        "clarification_answers_invalid": "补充条件不完整或格式不正确，请按待补字段重新提交。",
        "conversation_unavailable": "当前对话无法恢复，请重新发起请求。",
        "thread_expired": "当前对话已过期，请重新发起请求。",
        "thread_cleared": "当前对话已清理，无法继续恢复。",
        "thread_already_resumed": "当前对话已经恢复过，不能重复执行。",
        "thread_version_conflict": "当前对话状态已经变化，请使用最新版本。",
        "thread_context_mismatch": "当前身份上下文与待补任务不一致，无法恢复。",
        "state_version_incompatible": "当前对话版本不兼容，请重新发起请求。",
        "budget_exhausted": "补充后仍无法确定任务，本次恢复已停止。",
        "thread_checkpoint_failed": "当前对话状态无法安全保存或更新，请重新发起请求。",
    }
    return messages.get(reason_code, "当前请求无法安全完成，请重新发起请求。")
