"""M43-E：一个 Agent task turn 的唯一执行 seam。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from engine.harness.contracts import AgentRunResult, HarnessRequest, RouteDecision
from engine.harness.graph import HarnessRuntime, run_harness
from engine.phase4b.task_boundary import TaskBoundary, TaskBoundaryError, TaskLifecycleFact, TaskProjection
from engine.governance import TrustedCaller
from engine.phase4b.task_runtime import NodeContext, TaskDelta, TaskState, TaskTransition, apply_delta, attach_evidence, project_node_contexts, understand_turn


@dataclass(frozen=True)
class TaskTurnRequest:
    """严格 task envelope 投影后的内部请求。"""

    harness_request: HarnessRequest
    action: Literal["start", "continue", "switch", "cancel"]
    task_id: str | None = None
    expected_version: int | None = None


@dataclass(frozen=True)
class TaskTurnResult:
    """Response/Trace/Eval 共用的唯一 task turn 事实。"""

    result: AgentRunResult
    action: str
    graph_invocation_count: int
    task_runtime_invocation_count: int
    task: TaskProjection | None
    delta: TaskDelta | None
    transition: TaskTransition | None
    node_contexts: tuple[NodeContext, ...]
    lifecycle: TaskLifecycleFact
    task_runtime: dict[str, object]


def run_task_turn(*, request: TaskTurnRequest, runtime: HarnessRuntime, boundary: TaskBoundary) -> TaskTurnResult:
    """理解、claim、状态转换、最多一次深 Harness、commit 收敛成同一事实。"""

    caller = request.harness_request.caller
    try:
        previous: TaskState | None = None
        claim: TaskProjection | None = None
        if request.action != "start":
            claim = boundary.claim(task_id=request.task_id or "", expected_version=request.expected_version or 0, caller=caller)
            previous = claim.state
        owner = boundary.owner_ref(caller)
        delta = understand_turn(request.harness_request.question, action=request.action, previous=previous)
        state, transition = apply_delta(previous, delta, owner_ref=owner)
        contexts = project_node_contexts(
            question=request.harness_request.question,
            state=state,
            delta=delta,
            prior_state_identity=previous.identity if previous else None,
        )
        if state.status == "clarification_required":
            result = _local_result("task_clarification_required", "请补充明确的指标和月份。", answer_status="clarification_required", caller_ref=caller.audit_ref if caller else None)
            if claim is None:
                task, lifecycle = boundary.start(caller=caller, state=state)
            else:
                task, lifecycle = boundary.commit(claim=claim, caller=caller, state=state)
            return TaskTurnResult(result, request.action, 0, 1, task, delta, transition, contexts, lifecycle, boundary.runtime_identity)
        if delta.category == "cancel":
            assert claim is not None
            task, lifecycle = boundary.commit(claim=claim, caller=caller, state=state, terminal_status="cancelled")
            result = _local_result("task_cancelled", "当前任务已取消。", caller_ref=caller.audit_ref if caller else None)
            return TaskTurnResult(result, request.action, 0, 1, task, delta, transition, contexts, lifecycle, boundary.runtime_identity)

        resolved_question = _execution_question(state)
        harness = request.harness_request
        deep_request = HarnessRequest(question=resolved_question, run_id=harness.run_id, caller=caller, active_sql_role=harness.active_sql_role, force_new_pipeline=harness.force_new_pipeline, schema_retrieval_profile=harness.schema_retrieval_profile, schema_fusion_strategy=harness.schema_fusion_strategy)
        result = run_harness(request=deep_request, runtime=runtime)
        refs = tuple(result.observation.evidence_refs) if result.observation else ()
        committed_state = attach_evidence(state, refs)
        transition = replace(
            transition,
            after_identity=committed_state.identity,
            changed_fields=tuple(dict.fromkeys((*transition.changed_fields, "evidence"))),
        )
        post_contexts = project_node_contexts(
            question=request.harness_request.question,
            state=committed_state,
            delta=delta,
            prior_state_identity=previous.identity if previous else None,
        )
        # 理解/route/SQL 的 fingerprint 保留执行前事实；controller 才能看到本轮新 EvidenceRef。
        contexts = (*contexts[:3], post_contexts[3])
        if request.action == "start":
            task, lifecycle = boundary.start(caller=caller, state=committed_state)
        elif request.action == "switch":
            assert claim is not None
            task, lifecycle = boundary.switch(claim=claim, caller=caller, state=committed_state)
        else:
            assert claim is not None
            task, lifecycle = boundary.commit(claim=claim, caller=caller, state=committed_state)
        return TaskTurnResult(result, request.action, 1, 1, task, delta, transition, contexts, lifecycle, boundary.runtime_identity)
    except TaskBoundaryError as exc:
        result = _local_result(exc.reason_code, _message(exc.reason_code), safety_status=exc.safety_status, caller_ref=caller.audit_ref if caller else None)
        lifecycle = boundary.lifecycle_rejection(request.task_id or "", exc.reason_code)
        return TaskTurnResult(result, "rejected", 0, 0, None, None, None, (), lifecycle, boundary.runtime_identity)


def clear_task(*, task_id: str, expected_version: int, caller: TrustedCaller | None, boundary: TaskBoundary) -> tuple[TaskProjection | None, TaskLifecycleFact, bool, str]:
    """将 boundary clear 的成功/失败收敛为 API 可投影结果。"""

    try:
        task, lifecycle = boundary.clear(task_id=task_id, expected_version=expected_version, caller=caller)
        return task, lifecycle, True, "task_cleared"
    except TaskBoundaryError as exc:
        return None, boundary.lifecycle_rejection(task_id, exc.reason_code), False, exc.reason_code


def _execution_question(state: TaskState) -> str:
    """从已确认 state 重建本轮完整深 Tool 问题，绝不拼接自由历史。"""

    constraints = dict(state.constraints)
    periods = tuple(constraints.get("periods", ()))
    if constraints.get("metric") == "net_refund_amount" and len(periods) == 1:
        year, month = periods[0].split("-")
        return f"查询 {year} 年 {int(month)} 月实际净退款金额。"
    if constraints.get("metric") == "net_refund_amount" and len(periods) >= 2:
        left, right = periods[-2:]
        return f"查询 {left} 和 {right} 的实际净退款金额，并计算差额和变化率。"
    return state.goal


def _local_result(reason: str, answer: str, *, answer_status: str = "no_answer", safety_status: str = "passed", caller_ref: str | None) -> AgentRunResult:
    """为澄清、取消和 pre-rejection 形成兼容四轴结果，Graph 次数保持零。"""

    # Task clarification 不复用 M36 的字段表单合同；它由 task projection 的 pending_questions 表达。
    termination = "blocked" if safety_status == "blocked" else "answer"
    decision = RouteDecision("none", reason, False, termination, decision_source="controller")
    return AgentRunResult("none", "not_started" if safety_status == "blocked" or answer_status == "clarification_required" else "completed", answer_status, safety_status, reason, answer, decision, None, decision.termination_action, ("task_runtime",), caller_ref)


def _message(reason: str) -> str:
    """把内部 lifecycle reason 单向映射为安全用户文案。"""

    return {"task_unavailable": "当前任务不可用，请重新发起。", "task_expired": "当前任务已过期，请重新发起。", "task_version_conflict": "任务状态已经变化，请使用最新版本。", "task_not_active": "当前任务已经结束。"}.get(reason, "当前任务无法继续。")
