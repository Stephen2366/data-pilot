"""M43-E：一个 Agent task turn 的唯一执行 seam。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from engine.harness.contracts import AgentRunResult, HarnessRequest, RouteDecision
from engine.harness.graph import HarnessRuntime
from engine.phase4b.agent_loop import AgentLoopResult, AgentLoopRuntime, run_agent_loop
from engine.phase4b.knowledge_runtime import KnowledgeRuntimeResolver
from engine.phase4b.loop_contracts import AgentNodeContext
from engine.phase4b.task_boundary import TaskBoundaryError, TaskBoundaryEvent, TaskBoundaryPort, TaskLifecycleFact, TaskProjection, TaskStatusProjection
from engine.phase4b.task_context import (
    CompactDecision,
    TaskContextBuilder,
    TaskContextError,
    TaskContextWindow,
    TaskResultDigest,
)
from engine.governance import TrustedCaller
from engine.phase4b.task_runtime import NodeContext, TaskDelta, TaskState, TaskTransition, apply_delta, project_node_contexts, understand_turn


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
    node_contexts: tuple[NodeContext | AgentNodeContext, ...]
    lifecycle: TaskLifecycleFact
    task_runtime: dict[str, object]
    agent_loop: AgentLoopResult | None = None
    compact_decision: CompactDecision | None = None


def run_task_turn(
    *,
    request: TaskTurnRequest,
    runtime: HarnessRuntime,
    boundary: TaskBoundaryPort,
    agent_runtime: AgentLoopRuntime | None = None,
    context_builder: TaskContextBuilder | None = None,
) -> TaskTurnResult:
    """理解、claim、状态转换、最多一次深 Harness、commit 收敛成同一事实。"""

    caller = request.harness_request.caller
    builder = context_builder or TaskContextBuilder()
    try:
        previous: TaskState | None = None
        claim: TaskProjection | None = None
        if request.action != "start":
            claim = boundary.claim(task_id=request.task_id or "", expected_version=request.expected_version or 0, caller=caller, active_role=request.harness_request.active_sql_role)
            previous = claim.state
        # switch 会原子退役旧 task 并创建 version=1 的新 task。旧窗口只能用于授权和
        # lifecycle fencing，不能进入新 task 的 Context lineage，否则旧 ordinal/version
        # 会与新 lineage 的首轮 version=1 冲突，也会把旧任务历史错误带进新任务。
        starts_new_context_lineage = request.action in {"start", "switch"}
        base_context = (
            TaskContextWindow.empty()
            if starts_new_context_lineage
            else claim.context if claim and claim.context else TaskContextWindow.empty()
        )
        owner = boundary.owner_ref(caller)
        delta = understand_turn(request.harness_request.question, action=request.action, previous=previous)
        state, transition = apply_delta(previous, delta, owner_ref=owner)
        # M48：所有 task 节点只跨这个统一 builder seam 取 Context。start 没有历史 source，
        # 因而不会在首轮错误触发 compact；continue/switch 才对已提交窗口执行 dual trigger。
        candidate_contexts = builder.project_node_contexts(
            question=request.harness_request.question,
            state=state,
            delta=delta,
            prior_state_identity=None if starts_new_context_lineage else previous.identity if previous else None,
            window=base_context,
        )
        if starts_new_context_lineage:
            prepared_context = base_context
            compact_decision = CompactDecision(
                "not_triggered", "task_compact_not_triggered", None,
                base_context.identity, base_context.identity, None, 0.0,
            )
        else:
            prepared_context, compact_decision = builder.prepare(
                window=base_context, state=previous, candidate_contexts=candidate_contexts,
            )
        contexts = builder.project_node_contexts(
            question=request.harness_request.question, state=state, delta=delta,
            prior_state_identity=None if starts_new_context_lineage else previous.identity if previous else None,
            window=prepared_context,
        )
        if state.status == "clarification_required":
            local_contexts = (_as_agent_context(contexts[0]), _as_agent_context(contexts[3]))
            result = _local_result("task_clarification_required", "请补充明确的指标和月份。", answer_status="clarification_required", caller_ref=caller.audit_ref if caller else None)
            committed_context = builder.append_committed_turn(
                window=prepared_context, question=request.harness_request.question,
                version_after=1 if claim is None else claim.task_version + 1,
                delta=delta, state=state, action_count=0,
                termination_reason=None, budget_identity=None,
            )
            if claim is None:
                task, lifecycle = boundary.start(caller=caller, state=state, active_role=request.harness_request.active_sql_role, event=_event(delta, transition, None, committed_context), context=committed_context)
            else:
                task, lifecycle = boundary.commit(claim=claim, caller=caller, state=state, active_role=request.harness_request.active_sql_role, event=_event(delta, transition, None, committed_context), context=committed_context)
            return TaskTurnResult(result, request.action, 0, 1, task, delta, transition, local_contexts, lifecycle, _runtime_identity(boundary, builder), compact_decision=compact_decision)
        if delta.category == "cancel":
            local_contexts = (_as_agent_context(contexts[0]), _as_agent_context(contexts[3]))
            assert claim is not None
            task, lifecycle = boundary.commit(claim=claim, caller=caller, state=state, terminal_status="cancelled", active_role=request.harness_request.active_sql_role, event=_event(delta, transition, None, prepared_context), context=prepared_context)
            result = _local_result("task_cancelled", "当前任务已取消。", caller_ref=caller.audit_ref if caller else None)
            return TaskTurnResult(result, request.action, 0, 1, task, delta, transition, local_contexts, lifecycle, _runtime_identity(boundary, builder), compact_decision=compact_decision)

        if delta.category == "ask_about_existing_result":
            # ★ T6 restart 只读取原子恢复的 Context digest，不重跑 SQL/RAG/LLM。
            # digest 不存在时明确要求重新查询，绝不从 EvidenceRef 猜数值或正文。
            digest = prepared_context.latest_result_digest
            local_contexts = (_as_agent_context(contexts[0]), _as_agent_context(contexts[3]))
            if digest is None:
                result = _local_result(
                    "existing_result_digest_missing",
                    "当前任务没有可重放的结果摘要，请明确要求重新查询。",
                    caller_ref=caller.audit_ref if caller else None,
                )
                termination_reason = "no_progress"
            else:
                result = _local_result(
                    "existing_result_digest_ready", digest.summary_text,
                    answer_status="complete", caller_ref=caller.audit_ref if caller else None,
                )
                termination_reason = "answer_ready"
            committed_context = builder.append_committed_turn(
                window=prepared_context, question=request.harness_request.question,
                version_after=claim.task_version + 1 if claim else 1,
                delta=delta, state=state, action_count=0,
                termination_reason=termination_reason, budget_identity=None,
                result_digest=digest,
            )
            assert claim is not None
            task, lifecycle = boundary.commit(
                claim=claim, caller=caller, state=state,
                active_role=request.harness_request.active_sql_role,
                event=_event(
                    delta, transition, None, committed_context,
                    termination_reason=termination_reason,
                ),
                context=committed_context,
            )
            return TaskTurnResult(
                result, request.action, 0, 1, task, delta, transition, local_contexts,
                lifecycle, _runtime_identity(boundary, builder), compact_decision=compact_decision,
            )

        resolved_question = _execution_question(state)
        harness = request.harness_request
        deep_request = HarnessRequest(
            question=resolved_question, run_id=harness.run_id, caller=caller,
            active_sql_role=harness.active_sql_role, force_new_pipeline=harness.force_new_pipeline,
            schema_retrieval_profile=harness.schema_retrieval_profile,
            schema_fusion_strategy=harness.schema_fusion_strategy,
            base_aggregate_only=bool(dict(state.constraints).get("comparison")),
        )
        # M44：task family 的唯一 Graph 是独立 Decision Loop。未显式注入 resolver 的旧
        # direct caller 仍能跑 SQL-only task，但 registry 为空，绝不把 legacy RAG 当 fallback。
        active_agent_runtime = agent_runtime or AgentLoopRuntime(
            sql_tool=runtime.sql_tool,
            knowledge_resolver=KnowledgeRuntimeResolver(()),
            hybrid_synthesizer=runtime.hybrid_synthesizer,
        )
        loop = run_agent_loop(
            request=deep_request, state=state, runtime=active_agent_runtime,
            task_context=prepared_context.safe_projection(),
        )
        result = loop.result
        committed_state = loop.state
        committed_projection = committed_state.safe_projection()
        pre_loop_projection = state.safe_projection()
        loop_changed = tuple(
            key for key, value in committed_projection.items() if pre_loop_projection.get(key) != value
        )
        transition = replace(
            transition,
            after_identity=committed_state.identity,
            changed_fields=tuple(dict.fromkeys((*transition.changed_fields, *loop_changed))),
        )
        # 只保留实际执行节点：turn_understanding + Loop 的 decision/action/controller response。
        contexts = (_as_agent_context(contexts[0]), *loop.contexts)
        budget_identity = loop.budget.safe_projection().get("identity") or loop.budget.profile.identity
        committed_context = builder.append_committed_turn(
            window=prepared_context, question=request.harness_request.question,
            version_after=1 if request.action in {"start", "switch"} else claim.task_version + 1,
            delta=delta, state=committed_state, action_count=len(loop.attempts),
            termination_reason=loop.termination.reason, budget_identity=str(budget_identity),
            result_digest=_make_result_digest(result, committed_state),
        )
        if request.action == "start":
            task, lifecycle = boundary.start(caller=caller, state=committed_state, active_role=harness.active_sql_role, event=_event(delta, transition, loop, committed_context), context=committed_context)
        elif request.action == "switch":
            assert claim is not None
            task, lifecycle = boundary.switch(claim=claim, caller=caller, state=committed_state, active_role=harness.active_sql_role, event=_event(delta, transition, loop, committed_context), context=committed_context)
        else:
            assert claim is not None
            task, lifecycle = boundary.commit(claim=claim, caller=caller, state=committed_state, active_role=harness.active_sql_role, event=_event(delta, transition, loop, committed_context), context=committed_context)
        return TaskTurnResult(
            result, request.action, 1, 1, task, delta, transition, contexts,
            lifecycle, _runtime_identity(boundary, builder), loop, compact_decision,
        )
    except TaskBoundaryError as exc:
        result = _local_result(exc.reason_code, _message(exc.reason_code), safety_status=exc.safety_status, caller_ref=caller.audit_ref if caller else None)
        lifecycle = boundary.lifecycle_rejection(request.task_id or "", exc.reason_code)
        return TaskTurnResult(result, "rejected", 0, 0, None, None, None, (), lifecycle, _runtime_identity(boundary, builder))
    except TaskContextError as exc:
        result = _local_result(exc.reason_code, _message(exc.reason_code), safety_status="blocked", caller_ref=caller.audit_ref if caller else None)
        lifecycle = boundary.lifecycle_rejection(request.task_id or "", exc.reason_code)
        return TaskTurnResult(result, "rejected", 0, 0, None, None, None, (), lifecycle, _runtime_identity(boundary, builder))


def clear_task(*, task_id: str, expected_version: int, caller: TrustedCaller | None, boundary: TaskBoundaryPort, active_role: str | None = None) -> tuple[TaskProjection | None, TaskLifecycleFact, bool, str]:
    """将 boundary clear 的成功/失败收敛为 API 可投影结果。"""

    try:
        task, lifecycle = boundary.clear(task_id=task_id, expected_version=expected_version, caller=caller, active_role=active_role)
        return task, lifecycle, True, "task_cleared"
    except TaskBoundaryError as exc:
        return None, boundary.lifecycle_rejection(task_id, exc.reason_code), False, exc.reason_code


def read_task_status(
    *, task_id: str, caller: TrustedCaller | None, boundary: TaskBoundaryPort,
    active_role: str | None = None,
) -> tuple[TaskStatusProjection | None, TaskLifecycleFact, bool, str]:
    """将 adapter 的只读 status 成功/拒绝统一成 API 可安全投影的结果。

    ★ 这里与 ``clear_task`` 共用同一错误收口，但 status 不 claim、不改版本；页面只能据此
    恢复 last-acknowledged identity，不能借恢复接口重放上一条 mutation。
    """

    try:
        task, lifecycle = boundary.status(task_id=task_id, caller=caller, active_role=active_role)
        return task, lifecycle, True, "task_status_ready"
    except TaskBoundaryError as exc:
        return None, boundary.lifecycle_rejection(task_id, exc.reason_code), False, exc.reason_code


def _as_agent_context(context: NodeContext | AgentNodeContext) -> AgentNodeContext:
    """把 M43 legacy Context 投影到 M44 v2；不修改 v2 artifact 的旧 serializer。"""

    if isinstance(context, AgentNodeContext):
        return context
    return AgentNodeContext(
        purpose=context.purpose, source_identities=context.source_identities,
        payload=context.payload, allowed_fields=tuple(context.payload),
        field_budget=context.field_budget, token_budget=768,
    )


def _event(
    delta: TaskDelta,
    transition: TaskTransition,
    loop: AgentLoopResult | None,
    context: TaskContextWindow,
    *,
    termination_reason: str | None = None,
) -> TaskBoundaryEvent:
    """从本 turn 同源 typed fact 形成最小持久事件，不写 question/answer/rows。"""

    turn = context.uncovered_turns[-1] if context.uncovered_turns else None
    return TaskBoundaryEvent(
        delta_category=delta.category,
        transition_identity=transition.after_identity,
        action_count=len(loop.attempts) if loop else 0,
        termination_reason=loop.termination.reason if loop else termination_reason,
        turn_ordinal=turn.ordinal if turn else None, state_identity=transition.after_identity,
        constraint_keys=turn.constraint_keys if turn else (),
        requirement_identities=turn.requirement_identities if turn else (),
        active_evidence_identities=turn.active_evidence_identities if turn else (),
        budget_identity=turn.budget_identity if turn else None,
        context_identity=context.identity,
        compact_identity=context.compact.identity if context.compact else None,
        schema_version="phase4b-task-boundary-event-v2",
    )


def _runtime_identity(boundary: TaskBoundaryPort, builder: TaskContextBuilder) -> dict[str, object]:
    """将存储与 Context Builder identity 合并为同源 task runtime 事实。"""

    return {
        **dict(boundary.runtime_identity),
        "context_runtime_identity": "phase4b-task-context-runtime-v1",
        "context_builder_identity": builder.identity,
    }


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


def _make_result_digest(result: AgentRunResult, state: TaskState) -> TaskResultDigest | None:
    """只固化最近一次完整、安全回答；按 UTF-8 上限确定性截断，不保存 Tool 私有载荷。"""

    if result.answer_status != "complete" or result.safety_status != "passed" or not result.answer.strip():
        return None
    raw = result.answer.encode("utf-8")
    summary = result.answer if len(raw) <= 8192 else raw[:8189].decode("utf-8", errors="ignore").rstrip() + "…"
    evidence_ids = tuple(dict.fromkeys(
        str(item.ref.get("evidence_id"))
        for item in state.evidence
        if item.validity == "active" and item.ref.get("evidence_id")
    ))[-16:]
    return TaskResultDigest(
        route=result.route, answer_status="complete", summary_text=summary,
        evidence_ids=evidence_ids,
    )


def _local_result(reason: str, answer: str, *, answer_status: str = "no_answer", safety_status: str = "passed", caller_ref: str | None) -> AgentRunResult:
    """为澄清、取消和 pre-rejection 形成兼容四轴结果，Graph 次数保持零。"""

    # Task clarification 不复用 M36 的字段表单合同；它由 task projection 的 pending_questions 表达。
    termination = "blocked" if safety_status == "blocked" else "answer"
    decision = RouteDecision("none", reason, False, termination, decision_source="controller")
    return AgentRunResult("none", "not_started" if safety_status == "blocked" or answer_status == "clarification_required" else "completed", answer_status, safety_status, reason, answer, decision, None, decision.termination_action, ("task_runtime",), caller_ref)


def _message(reason: str) -> str:
    """把内部 lifecycle reason 单向映射为安全用户文案。"""

    return {"task_unavailable": "当前任务不可用，请重新发起。", "task_expired": "当前任务已过期，请重新发起。", "task_version_conflict": "任务状态已经变化，请使用最新版本。", "task_not_active": "当前任务已经结束。", "task_compact_source_incomplete": "当前任务缺少可验证的历史上下文，请重新发起。", "task_context_budget_exceeded": "当前任务上下文已达到安全上限，请缩小问题范围。"}.get(reason, "当前任务无法继续。")
