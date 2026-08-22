"""M35–M37 `/api/query`：把 HTTP 请求投影到唯一的 turn-level Harness。

★ API 不自行选择 Text2SQL、管理 checkpoint 或拼安全状态。它只解析 caller、注入依赖，
再把 `AgentTurnResult` 单向投影成兼容响应与 JSONL Trace。
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentResponse, CostInfo, QueryRequest, ThreadControlResponse, ThreadView
from engine.harness.adapters import RAGToolAdapter, Text2SQLToolAdapter
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.graph import HarnessRuntime
from engine.harness.thread import ThreadCheckpointManager
from engine.harness.turn import AgentTurnResult, TurnRequest, clear_thread, run_turn
from engine.trace.recorder import TraceRecord, append_trace
from engine.trace.runtime import build_trace_runtime_identity


router = APIRouter(prefix="/api", tags=["query"])


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
    return {
        "tool_name": observation.tool_name,
        "route": observation.route,
        "execution_status": observation.execution_status,
        "answer_status": observation.answer_status,
        "safety_status": observation.safety_status,
        "reason_code": observation.reason_code,
        "error_type": observation.error_type,
        "sql_time_ms": observation.sql_time_ms,
        "diagnostics": observation.diagnostics,
        "ledger": observation.ledger_projection,
    }


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
    *, request: Request, request_body: QueryRequest, response: AgentResponse, turn: AgentTurnResult
) -> None:
    """把同一份 Harness result 写成 JSONL 安全投影，Trace 不重新判断 route 或四轴。"""

    result = turn.result
    observation = result.observation
    hybrid_branches = _hybrid_branch_projection(result)
    decision = result.route_decision
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
        trace_steps=list(observation.trace_steps) if observation else [],
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
        runtime_identity=build_trace_runtime_identity(result=result, checkpoint_runtime=turn.checkpoint_runtime),
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
    rag_tool = rag_tool_factory() if rag_tool_factory is not None else RAGToolAdapter()
    runtime = HarnessRuntime(
        sql_tool=Text2SQLToolAdapter(db=db, schema_vector_index=getattr(request.app.state, "schema_vector_index", None)),
        rag_tool=rag_tool,
        router=getattr(request.app.state, "harness_router", None),
    )
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
