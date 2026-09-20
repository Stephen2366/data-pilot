"""M35–M37 `/api/query`：把 HTTP 请求投影到唯一的 turn-level Harness。

★ API 不自行选择 Text2SQL、管理 checkpoint 或拼安全状态。它只解析 caller、注入依赖，
再把 `AgentTurnResult` 单向投影成兼容响应与 JSONL Trace。
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentResponse, CostInfo, QueryRequest, TaskControlResponse, TaskStatusResponse, TaskStatusView, TaskView, ThreadControlResponse, ThreadView, ToolCallTrace
from engine.harness.adapters import RAGToolAdapter, Text2SQLToolAdapter, UnavailableRAGToolAdapter
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import AgentTurnResult, TurnRequest, clear_thread, run_turn
from engine.trace.recorder import TraceRecord, TraceStep, append_trace
from engine.trace.runtime import build_trace_runtime_identity
from engine.phase4b.task_boundary import TaskBoundaryPort
from engine.phase4b.task_turn import TaskTurnRequest, TaskTurnResult, clear_task, read_task_status, run_task_turn
from engine.phase4b.agent_loop import AgentLoopRuntime
from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.b5_contracts import load_b5_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.knowledge_runtime import KnowledgeRuntimeResolver, KnowledgeRuntimeSpec
from engine.phase4b.scenario_projection import agent_scenario_source_identity


router = APIRouter(prefix="/api", tags=["query"])
B4_BUNDLE = load_b4_contract_bundle()
B5_BUNDLE = load_b5_contract_bundle()
_SAFE_SQL_EXECUTION_MESSAGE = "SQL 执行失败。"


def _trace_id(request: Request) -> str:
    """从日志中间件读取 trace_id，保证响应体、响应头和 Harness run identity 一致。"""

    return getattr(request.state, "trace_id", "unknown")


def _trace_path(request: Request) -> Path | None:
    """读取测试或运行时指定的 JSONL 目标，默认仍由 recorder 使用正式路径。"""

    path = getattr(request.app.state, "trace_path", None)
    return Path(path) if path is not None else None


def _observation_projection(observation: ToolObservation | None) -> dict[str, Any] | None:
    """为 Trace/Eval 形成白名单 Observation，不携带 RAG 文档正文或内部异常文本。"""

    if observation is None:
        return None
    safe_diagnostics = {
        key: value for key, value in observation.diagnostics.items()
        if key.lower() not in {"technical_message", "raw_error", "stack", "prompt", "rows", "thought"}
    }
    return {
        "tool_name": observation.tool_name,
        "route": observation.route,
        "execution_status": observation.execution_status,
        "answer_status": observation.answer_status,
        "safety_status": observation.safety_status,
        "reason_code": observation.reason_code,
        "error_type": observation.error_type,
        "sql_time_ms": observation.sql_time_ms,
        "diagnostics": safe_diagnostics,
        "ledger": observation.ledger_projection,
    }


def _safe_tool_calls(calls: list[ToolCallTrace]) -> list[ToolCallTrace]:
    """在公开边界再次脱敏 SQL 执行错误，防止 adapter 误把 driver 原文透传出去。"""

    return [
        call.model_copy(update={"message": _SAFE_SQL_EXECUTION_MESSAGE})
        if call.error_type == "sql_execution_error"
        else call
        for call in calls
    ]


def _safe_trace_steps(steps: tuple[Any, ...]) -> list[Any]:
    """清理 SQL execution span；Response 与 JSONL Trace 共守同一 raw-error 禁区。"""

    projected: list[Any] = []
    for step in steps:
        if isinstance(step, TraceStep) and step.error_type == "sql_execution_error":
            safe_metadata = {
                key: value
                for key, value in step.metadata.items()
                if key in {"tables_used", "latency_ms", "issue_code"}
            }
            projected.append(step.model_copy(update={
                "output_summary": _SAFE_SQL_EXECUTION_MESSAGE,
                "metadata": safe_metadata,
            }))
        else:
            projected.append(step)
    return projected


def _hybrid_branch_projection(result: Any) -> list[dict[str, Any]]:
    """形成 Hybrid branch 的最小安全摘要；拒绝分支不暴露 EvidenceRef 或内部 reason。"""

    if result.hybrid is None:
        return []
    projected: list[dict[str, Any]] = []
    for branch in result.hybrid.branches:
        observation = branch.observation
        allowed = observation.safety_status == "passed" and branch.evidence_ready
        projected.append(
            {
                "branch": branch.branch,
                "execution_status": observation.execution_status,
                "answer_status": observation.answer_status,
                "safety_status": observation.safety_status,
                "reason_code": observation.reason_code if observation.safety_status == "passed" else "branch_not_disclosed",
                "evidence_refs": list(observation.evidence_refs) if allowed else [],
            }
        )
    return projected


def _project_response(*, turn: AgentTurnResult, trace_id: str, started_at: float) -> AgentResponse:
    """★ 唯一 AgentResponse projector：旧字段只从同一份 Harness 事实派生。"""

    result = turn.result
    observation = result.observation
    hybrid_branches = _hybrid_branch_projection(result)
    # 步骤 1：从 Observation 取得兼容字段；none 路径不会伪造 SQL、rows 或 docs。----------
    hybrid_sql = result.hybrid.branch("sql").observation if result.hybrid is not None else None
    sql = observation.sql if observation else (hybrid_sql.sql if hybrid_sql else None)
    columns = list(observation.columns) if observation else (list(hybrid_sql.columns) if hybrid_sql else [])
    rows = list(observation.rows) if observation else (list(hybrid_sql.rows) if hybrid_sql else [])
    tables_used = list(observation.tables_used) if observation else (list(hybrid_sql.tables_used) if hybrid_sql else [])
    docs_used = list(observation.docs_used) if observation else []
    chart_spec = observation.chart_spec if observation else (hybrid_sql.chart_spec if hybrid_sql else None)
    tool_calls = list(observation.tool_calls) if observation else (
        [call for branch in result.hybrid.branches for call in branch.observation.tool_calls] if result.hybrid else []
    )
    tool_calls = _safe_tool_calls(tool_calls)
    citations = list(observation.citations) if observation else (list(result.hybrid.citations) if result.hybrid else [])

    # 步骤 2：blocked_reason 只表达安全裁决；技术故障只能在 reason/error_type 中诊断。----
    blocked_reason = observation.blocked_reason if observation and result.safety_status == "blocked" else None
    return AgentResponse(
        route=result.route,
        answer=result.answer,
        sql=sql,
        columns=columns,
        rows=rows,
        tables_used=tables_used,
        docs_used=docs_used,
        chart_spec=chart_spec,
        safety_status=result.safety_status,
        blocked_reason=blocked_reason,
        cost=CostInfo(
            latency_ms=round((perf_counter() - started_at) * 1000, 3),
            sql_time_ms=observation.sql_time_ms if observation else (hybrid_sql.sql_time_ms if hybrid_sql else 0.0),
        ),
        tool_calls=tool_calls,
        error_type=observation.error_type if observation else (result.reason_code if result.execution_status == "failed" else None),
        trace_id=trace_id,
        execution_status=result.execution_status,
        answer_status=result.answer_status,
        citations=citations,
        reason_code=result.reason_code,
        turn_action=turn.turn_action,
        graph_invocation_count=turn.graph_invocation_count,
        thread=ThreadView.model_validate(turn.thread.as_dict()) if turn.thread else None,
        hybrid_branches=hybrid_branches,
    )


def _record_trace(
    *, request: Request, request_body: QueryRequest, response: AgentResponse, turn: AgentTurnResult,
    task_turn: TaskTurnResult | None = None,
) -> None:
    """把同一份 Harness result 写成 JSONL 安全投影，Trace 不重新判断 route 或四轴。"""

    result = turn.result
    observation = result.observation
    hybrid_branches = _hybrid_branch_projection(result)
    decision = result.route_decision
    deep_runtime_identity = build_trace_runtime_identity(
        result=result, checkpoint_runtime=turn.checkpoint_runtime
    )
    runtime_identity = deep_runtime_identity
    if task_turn is not None:
        # B5 是 durable task envelope 的顶层合同；父 Agent Loop 自己仍在 agent_loop
        # runtime 内声明 B2/B4，避免把持久化边界和检索策略混成一个 identity。
        runtime_identity = {
            "format": "phase4b-agent-task-runtime-v1",
            "status": "complete",
            "contract_identity": B5_BUNDLE.content_identity,
            "predecessor_contract_identity": B4_BUNDLE.content_identity,
            "task_state_version": task_turn.task.state.state_version if task_turn.task else None,
            "turn_understanding_identity": task_turn.delta.source_identity if task_turn.delta else None,
            "task_boundary": task_turn.task_runtime,
            "deep_harness": deep_runtime_identity,
            "agent_loop": task_turn.agent_loop.runtime_identity if task_turn.agent_loop else None,
        }
    trace_record = TraceRecord(
        trace_id=response.trace_id,
        question=request_body.question,
        user_role=request_body.user_role,
        route=response.route,
        answer=response.answer,
        sql=response.sql,
        columns=response.columns,
        # Hybrid 的完整 SQL rows 只保留在本次 API 兼容视图，默认 JSONL 仅保存 result identity；
        # 否则两支 private Evidence 会被 Trace 旁路长期化。
        rows=[] if result.hybrid is not None else response.rows,
        tables_used=response.tables_used,
        docs_used=response.docs_used,
        chart_spec=response.chart_spec,
        safety_status=response.safety_status,
        blocked_reason=response.blocked_reason,
        cost=response.cost,
        tool_calls=response.tool_calls,
        trace_steps=_safe_trace_steps(observation.trace_steps) if observation else [],
        error_type=response.error_type,
        langfuse_trace_id=observation.langfuse_trace_id if observation else None,
        langfuse_trace_url=observation.langfuse_trace_url if observation else None,
        langfuse_write_status=observation.langfuse_write_status if observation else "skipped",
        langfuse_span_mode=observation.langfuse_span_mode if observation else "post_hoc",
        execution_status=result.execution_status,
        answer_status=result.answer_status,
        reason_code=result.reason_code,
        route_decision={
            "route": decision.route,
            "reason_code": decision.reason_code,
            "needs_evidence": decision.needs_evidence,
            "termination_action": decision.termination_action,
            "decision_source": decision.decision_source,
            "requirement_identity": decision.requirement.identity if decision.requirement else None,
            "clarification": decision.clarification_spec.safe_projection() if decision.clarification_spec else None,
            "hybrid_plan_identity": decision.hybrid_plan.identity if decision.hybrid_plan else None,
            "router_evidence": decision.router_evidence.safe_projection() if decision.router_evidence else None,
        },
        graph_steps=list(result.graph_steps),
        caller_safe_ref=result.caller_safe_ref,
        tool_observation=_observation_projection(observation),
        evidence_refs=list(observation.evidence_refs) if observation else [],
        termination_action=result.termination_action,
        hybrid_branches=hybrid_branches,
        turn_action=turn.turn_action,
        graph_invocation_count=turn.graph_invocation_count,
        thread_lifecycle=turn.lifecycle.safe_projection() if turn.lifecycle else None,
        checkpoint_runtime=turn.checkpoint_runtime,
        runtime_identity=runtime_identity,
        runtime_family=response.runtime_family,
        task_action=response.task_action,
        task_runtime_invocation_count=response.task_runtime_invocation_count,
        task_lifecycle=task_turn.lifecycle.safe_projection() if task_turn else None,
        task_state=task_turn.task.state.safe_projection() if task_turn and task_turn.task else None,
        task_delta=task_turn.delta.safe_projection() if task_turn and task_turn.delta else None,
        task_transition=task_turn.transition.safe_projection() if task_turn and task_turn.transition else None,
        node_contexts=[item.safe_projection() for item in task_turn.node_contexts] if task_turn else [],
        action_attempts=[item.safe_projection() for item in task_turn.agent_loop.attempts] if task_turn and task_turn.agent_loop else [],
        agent_budget=task_turn.agent_loop.budget.safe_projection() if task_turn and task_turn.agent_loop else None,
        agent_termination=task_turn.agent_loop.termination.safe_projection() if task_turn and task_turn.agent_loop else None,
        knowledge_runtimes=[dict(item) for item in task_turn.agent_loop.knowledge_runtimes] if task_turn and task_turn.agent_loop else [],
        agent_loop_runtime=dict(task_turn.agent_loop.runtime_identity) if task_turn and task_turn.agent_loop else None,
        agent_scenario_source_identity=response.agent_scenario_source_identity,
        task_context=task_turn.task.context.safe_projection() if task_turn and task_turn.task and task_turn.task.context else None,
        compact_decision=task_turn.compact_decision.safe_projection() if task_turn and task_turn.compact_decision else None,
    )
    path = _trace_path(request)
    if path is None:
        append_trace(trace_record)
    else:
        append_trace(trace_record, path=path)


@router.post("/query", response_model=AgentResponse)
def query(request_body: QueryRequest, request: Request, db: Session = Depends(get_db)) -> AgentResponse:
    """执行唯一 turn seam；旧单轮、clarification 和一次 follow-up 共用同一投影。"""

    started_at = perf_counter()
    trace_id = _trace_id(request)

    # 步骤 1：应用组装层的 resolver 解析 role；没有 resolver 或 role 不匹配时不调用任何 Tool。
    resolver = getattr(request.app.state, "caller_resolver", None)
    resolution = resolver.resolve(request_body.user_role) if resolver is not None else None
    harness_request = HarnessRequest(
        question=request_body.question,
        run_id=trace_id,
        caller=resolution.caller if resolution else None,
        active_sql_role=resolution.active_sql_role if resolution else None,
        force_new_pipeline=request_body.force_new_pipeline,
        schema_retrieval_profile=request_body.schema_retrieval_profile,
        schema_fusion_strategy=request_body.schema_fusion_strategy,
        enable_bounded_follow_up=request_body.enable_bounded_follow_up,
    )

    # 步骤 2：DB Session、深 Tool 与可选 Schema index 仅属于本次 invoke 的 runtime context。
    rag_tool_factory = getattr(request.app.state, "rag_tool_factory", None)
    # ★ M44A：None 不再表示“使用仓库内小语料”。产品 runtime 未配置/未就绪时，
    # RAG 路由明确 external_unavailable；Eval/测试若要替换，必须注入显式 factory。
    rag_tool = (
        rag_tool_factory()
        if rag_tool_factory is not None
        else UnavailableRAGToolAdapter(
            reason_code=str(
                getattr(request.app.state, "rag_runtime_status", {}).get(
                    "reason_code", "enterprise_rag_runtime_unavailable"
                )
            )
        )
    )
    sql_tool_factory = getattr(request.app.state, "sql_tool_factory", None)
    sql_tool = sql_tool_factory() if sql_tool_factory is not None else Text2SQLToolAdapter(
        db=db, schema_vector_index=getattr(request.app.state, "schema_vector_index", None)
    )
    runtime = HarnessRuntime(
        sql_tool=sql_tool,
        rag_tool=rag_tool,
        router=getattr(request.app.state, "harness_router", None),
    )
    if request_body.task is not None:
        boundary: TaskBoundaryPort = request.app.state.task_boundary
        runtime_specs: list[KnowledgeRuntimeSpec] = []
        business_factory = getattr(request.app.state, "business_rag_tool_factory", None)
        if business_factory is not None:
            runtime_specs.append(KnowledgeRuntimeSpec(
                "business_release", business_factory,
                str(getattr(request.app.state, "business_rag_runtime_identity", "business-release-active-v1")),
            ))
        if rag_tool_factory is not None:
            raw_external_identity = getattr(request.app.state, "rag_runtime_status", {}).get("runtime_identity")
            external_identity = (
                f"external-profile:{canonical_hash(raw_external_identity)}"
                if isinstance(raw_external_identity, dict) else str(raw_external_identity or "external-profile-active-v1")
            )
            runtime_specs.append(KnowledgeRuntimeSpec(
                "external_profile", rag_tool_factory, external_identity
            ))
        agent_runtime = AgentLoopRuntime(
            sql_tool=sql_tool,
            knowledge_resolver=KnowledgeRuntimeResolver(tuple(runtime_specs)),
            hybrid_synthesizer=runtime.hybrid_synthesizer,
            # 只读取 server state；客户端请求不能选择 B4 或绕过它的固定合同/预算。
            b4_enabled=bool(getattr(request.app.state, "b4_task_enabled", False)),
        )
        task_turn = run_task_turn(
            request=TaskTurnRequest(
                harness_request=harness_request,
                action=request_body.task.action,
                task_id=request_body.task.task_id,
                expected_version=request_body.task.expected_version,
            ),
            runtime=runtime,
            boundary=boundary,
            agent_runtime=agent_runtime,
        )
        # 复用兼容字段的唯一 projector，再只追加 task family 事实；SimpleNamespace 不参与业务判断。
        compatible_turn = SimpleNamespace(
            result=task_turn.result,
            turn_action="rejected" if task_turn.action == "rejected" else "initial",
            graph_invocation_count=task_turn.graph_invocation_count,
            thread=None,
            lifecycle=None,
            checkpoint_runtime=task_turn.task_runtime,
        )
        response = _project_response(turn=compatible_turn, trace_id=trace_id, started_at=started_at)
        response = response.model_copy(update={
            "runtime_family": "agent_task",
            "task_action": task_turn.action,
            "task_runtime_invocation_count": task_turn.task_runtime_invocation_count,
            "task": TaskView.model_validate(task_turn.task.safe_projection()) if task_turn.task else None,
            "task_delta": task_turn.delta.safe_projection() if task_turn.delta else None,
            "task_transition": task_turn.transition.safe_projection() if task_turn.transition else None,
            "node_contexts": [item.safe_projection() for item in task_turn.node_contexts],
            "action_attempts": [item.safe_projection() for item in task_turn.agent_loop.attempts] if task_turn.agent_loop else [],
            "agent_budget": task_turn.agent_loop.budget.safe_projection() if task_turn.agent_loop else None,
            "agent_termination": task_turn.agent_loop.termination.safe_projection() if task_turn.agent_loop else None,
            "knowledge_runtimes": [dict(item) for item in task_turn.agent_loop.knowledge_runtimes] if task_turn.agent_loop else [],
            "agent_loop_runtime": dict(task_turn.agent_loop.runtime_identity) if task_turn.agent_loop else None,
            "agent_scenario_source_identity": (
                agent_scenario_source_identity(
                    actions=[item.safe_projection() for item in task_turn.agent_loop.attempts],
                    budget=task_turn.agent_loop.budget.safe_projection(),
                    termination=task_turn.agent_loop.termination.safe_projection(),
                    runtime_identity=dict(task_turn.agent_loop.runtime_identity),
                )
                if task_turn.agent_loop else None
            ),
            "task_context": task_turn.task.context.safe_projection() if task_turn.task and task_turn.task.context else None,
            "compact_decision": task_turn.compact_decision.safe_projection() if task_turn.compact_decision else None,
        })
        _record_trace(request=request, request_body=request_body, response=response, turn=compatible_turn, task_turn=task_turn)
        return response

    checkpoint_manager: ThreadCheckpointManager = request.app.state.thread_checkpoint_manager
    turn = run_turn(
        request=TurnRequest(
            harness_request=harness_request,
            thread_id=request_body.thread_id,
            expected_version=request_body.expected_version,
            clarification_answers=request_body.clarification_answers,
            follow_up_action=request_body.follow_up_action,
            follow_up_fields=request_body.follow_up_fields,
        ),
        runtime=runtime,
        checkpoint_manager=checkpoint_manager,
    )
    response = _project_response(turn=turn, trace_id=trace_id, started_at=started_at)
    _record_trace(request=request, request_body=request_body, response=response, turn=turn)
    return response


@router.delete("/query/tasks/{task_id}", response_model=TaskControlResponse)
def clear_query_task(
    task_id: str,
    request: Request,
    user_role: str = Query(default="ops"),
    expected_version: int = Query(ge=1),
) -> TaskControlResponse:
    """由可信 owner/version 清理 task；clear 路径不调用深 Harness。"""

    resolver = getattr(request.app.state, "caller_resolver", None)
    resolution = resolver.resolve(user_role) if resolver is not None else None
    boundary: TaskBoundaryPort = request.app.state.task_boundary
    task, lifecycle, ok, reason = clear_task(
        task_id=task_id,
        expected_version=expected_version,
        caller=resolution.caller if resolution else None,
        boundary=boundary,
        active_role=resolution.active_sql_role if resolution else None,
    )
    safety = "passed" if ok else ("blocked" if reason == "task_unavailable" else "passed")
    message = "当前任务已清理。" if ok else "当前任务无法清理。"
    trace_record = TraceRecord(
        trace_id=_trace_id(request), question="[task-clear]", user_role=user_role, route="none", answer=message,
        safety_status=safety, cost=CostInfo(), execution_status="completed" if ok else "not_started",
        answer_status="no_answer", reason_code=reason, caller_safe_ref=resolution.caller.audit_ref if resolution else None,
        termination_action="answer" if ok else ("blocked" if safety == "blocked" else "failed"), turn_action="clear",
        graph_invocation_count=0, checkpoint_runtime=boundary.runtime_identity,
        runtime_identity={"format": "phase4b-task-runtime-v1", "status": "complete", "task_boundary": boundary.runtime_identity},
        runtime_family="agent_task", task_action="clear", task_runtime_invocation_count=0,
        task_lifecycle=lifecycle.safe_projection(), task_state=task.state.safe_projection() if task else None,
    )
    path = _trace_path(request)
    append_trace(trace_record, path=path) if path is not None else append_trace(trace_record)
    return TaskControlResponse(ok=ok, reason_code=reason, safety_status=safety, message=message, task=TaskView.model_validate(task.safe_projection()) if task else None)


@router.get("/query/tasks/{task_id}", response_model=TaskStatusResponse)
def get_query_task_status(
    task_id: str,
    request: Request,
    user_role: str = Query(default="ops"),
) -> TaskStatusResponse:
    """只读核对 unknown mutation 后的 task 版本/status，不调用 Graph 或消费 claim。"""

    resolver = getattr(request.app.state, "caller_resolver", None)
    resolution = resolver.resolve(user_role) if resolver is not None else None
    boundary: TaskBoundaryPort = request.app.state.task_boundary
    task, lifecycle, ok, reason = read_task_status(
        task_id=task_id,
        caller=resolution.caller if resolution else None,
        boundary=boundary,
        active_role=resolution.active_sql_role if resolution else None,
    )
    safety = "passed" if ok else ("blocked" if reason == "task_unavailable" else "passed")
    message = "任务状态已核对。" if ok else "当前任务状态不可用。"
    trace_record = TraceRecord(
        trace_id=_trace_id(request), question="[task-status]", user_role=user_role, route="none", answer=message,
        safety_status=safety, cost=CostInfo(), execution_status="completed" if ok else "not_started",
        answer_status="no_answer", reason_code=reason, caller_safe_ref=resolution.caller.audit_ref if resolution else None,
        termination_action="answer" if ok else ("blocked" if safety == "blocked" else "failed"), turn_action="status",
        graph_invocation_count=0, checkpoint_runtime=boundary.runtime_identity,
        runtime_identity={"format": "phase4b-task-runtime-v1", "status": "complete", "task_boundary": boundary.runtime_identity},
        runtime_family="agent_task", task_action="status", task_runtime_invocation_count=0,
        task_lifecycle=lifecycle.safe_projection(), task_state=None,
    )
    path = _trace_path(request)
    append_trace(trace_record, path=path) if path is not None else append_trace(trace_record)
    return TaskStatusResponse(
        ok=ok, reason_code=reason, safety_status=safety, message=message,
        task=TaskStatusView.model_validate(task.safe_projection()) if task else None,
    )


@router.delete("/query/threads/{thread_id}", response_model=ThreadControlResponse)
def clear_query_thread(
    thread_id: str,
    request: Request,
    user_role: str = Query(default="ops"),
    expected_version: int = Query(ge=1),
) -> ThreadControlResponse:
    """显式清理 pending/resolved checkpoint；thread id 本身不能授权这个动作。"""

    resolver = getattr(request.app.state, "caller_resolver", None)
    resolution = resolver.resolve(user_role) if resolver is not None else None
    checkpoint_manager: ThreadCheckpointManager = request.app.state.thread_checkpoint_manager
    control = clear_thread(
        thread_id=thread_id,
        expected_version=expected_version,
        caller=resolution.caller if resolution else None,
        checkpoint_manager=checkpoint_manager,
    )

    # clear 没有业务 Graph/Tool，但仍写一条 lifecycle Trace，便于证明谁在何时让状态失效。
    trace_record = TraceRecord(
        trace_id=_trace_id(request),
        question="[thread-clear]",
        user_role=user_role,
        route="none",
        answer=control.message,
        safety_status=control.safety_status,
        cost=CostInfo(),
        execution_status="completed" if control.ok else "not_started",
        answer_status="no_answer",
        reason_code=control.reason_code,
        caller_safe_ref=resolution.caller.audit_ref if resolution else None,
        termination_action="answer" if control.ok else ("blocked" if control.safety_status == "blocked" else "failed"),
        turn_action="rejected" if not control.ok else "clear",
        graph_invocation_count=0,
        thread_lifecycle=control.lifecycle.safe_projection(),
        checkpoint_runtime=checkpoint_manager.runtime_identity,
        runtime_identity={
            "format": "phase4-trace-runtime-v1", "status": "complete",
            "harness_identity": "phase4-harness-langgraph-v1", "route": "none",
            "checkpoint_runtime": checkpoint_manager.runtime_identity,
            "route_runtime": {"kind": "thread_control", "reason_code": control.reason_code}, "missing": [],
        },
    )
    path = _trace_path(request)
    if path is None:
        append_trace(trace_record)
    else:
        append_trace(trace_record, path=path)
    return ThreadControlResponse(
        ok=control.ok,
        reason_code=control.reason_code,
        safety_status=control.safety_status,
        message=control.message,
        thread=ThreadView.model_validate(control.thread.as_dict()) if control.thread else None,
    )
