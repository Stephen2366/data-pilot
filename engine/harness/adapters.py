"""M35–M37 将 Text2SQL/RAG 深 module 适配为统一 ToolObservation。"""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from time import perf_counter
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session

from app.schemas.agent import ToolCallTrace
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.nl2sql.generator import LLMGenerationError, generate_sql
from engine.nl2sql.pipeline import Text2SQLPipelineResult, run_text2sql_pipeline
from engine.nl2sql.schema_loader import load_domain_schema
from engine.nl2sql.templates import match_template
from engine.rag.answer_flow import AnswerEvidenceRequirement, RAGAnswerFlow, RAGAnswerRequest
from engine.rag.evidence import EvidenceLedger, make_sql_evidence
from engine.sql_guard.guard import validate_readonly_sql
from engine.sql_guard.precheck import looks_like_dangerous_sql
from engine.tools.chart_tool import build_chart_spec
from engine.tools.sql_tool import SQLToolResult, run_sql_tool


class Text2SQLTool(Protocol):
    """Text2SQL 深 module 的 Harness seam。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        """执行完整 SQL 流水线，返回统一四轴 Observation。"""

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        """执行同一 SQL 深链并保留仅供 Hybrid controller 消费的 typed Evidence。"""


class RAGTool(Protocol):
    """RAGAnswerFlow 深 module 的 Harness seam。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        """执行一次既有 AnswerFlow，不在 Graph 内重写其 Gate/Composer/Validator。"""

    def run_for_hybrid(self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement) -> ToolObservation:
        """执行 retrieval + Gate，绝不生成一个 RAG 自然语言子答案。"""


def _result_fingerprint(columns: list[str], rows: list[dict[str, Any]]) -> str:
    """按 columns 顺序规范化结果，生成可复算 SQL Evidence fingerprint。"""

    normalized_rows = [[row.get(column) for column in columns] for row in rows]
    payload = json.dumps({"columns": columns, "rows": normalized_rows}, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _sql_observation(
    *,
    request: HarnessRequest,
    sql: str | None,
    answer_hint: str,
    tool_result: SQLToolResult | None,
    error_type: str | None,
    message: str | None,
    trace_steps: tuple[Any, ...] = (),
    chart_spec: dict[str, Any] | None = None,
    tool_call: ToolCallTrace | None = None,
    lifecycle: dict[str, str | None] | None = None,
    semantic_request_rejection: bool = False,
    output_projection_rejection: bool = False,
) -> ToolObservation:
    """集中区分确定性 SQL 合同拒绝与技术失败，避免旧 API 的“全都 blocked”回归。"""

    result = tool_result
    resolved_error = error_type or (result.error_type if result else None)
    resolved_call = tool_call or (result.tool_call if result else None)
    lifecycle = lifecycle or {}

    # 步骤 1：唯一安全失败是 Guard/policy；它已完成一次受控执行尝试，但不形成 Evidence。----
    if (result is not None and result.safety_status == "blocked" and result.error_type == "sql_guard_blocked") or (
        resolved_error == "sql_guard_blocked"
    ):
        reason = result.blocked_reason if result else message
        guard_call = resolved_call or ToolCallTrace(
            tool_name="sql_guard",
            status="blocked",
            sql=sql,
            error_type="sql_guard_blocked",
            message=reason,
        )
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="no_answer",
            safety_status="blocked",
            reason_code="sql_guard_blocked",
            answer="SQL Guard 已拦截该请求。",
            sql=sql,
            tool_calls=(guard_call,),
            trace_steps=tuple(trace_steps),
            blocked_reason=reason or "SQL Guard 已拦截。",
            error_type="sql_guard_blocked",
            sql_time_ms=result.sql_time_ms if result else 0.0,
            langfuse_trace_id=lifecycle.get("trace_id"),
            langfuse_trace_url=lifecycle.get("trace_url"),
            langfuse_write_status=lifecycle.get("write_status") or "skipped",
            langfuse_span_mode=lifecycle.get("span_mode") or "post_hoc",
        )

    # 已知字段/语义不支持是产品级确定性拒绝，不是模型或数据库技术故障。这个分支保留 M27
    # expected_rejection 的语义；普通 QueryPlan 生成/自检失败仍会走下面的技术失败映射。
    if semantic_request_rejection:
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="unsupported",
            safety_status="blocked",
            reason_code="semantic_request_validation",
            answer="当前数据模型不支持该查询请求。",
            sql=sql,
            tool_calls=(resolved_call,) if resolved_call else (),
            trace_steps=tuple(trace_steps),
            blocked_reason=message or "请求未通过数据模型语义校验。",
            error_type=resolved_error or "plan_validation_failed",
            langfuse_trace_id=lifecycle.get("trace_id"),
            langfuse_trace_url=lifecycle.get("trace_url"),
            langfuse_write_status=lifecycle.get("write_status") or "skipped",
            langfuse_span_mode=lifecycle.get("span_mode") or "post_hoc",
        )

    # QueryPlan 的输出投影校验也是确定性安全合同：候选 SQL 尚未执行，必须被阻止；但它和
    # LLM 解析失败不同，后者只是外部能力暂不可用。这个窄分支保留 Phase 3 的 SQL fidelity
    # 语义，又不让所有 pipeline 错误重新混进 safety。
    if output_projection_rejection:
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="no_answer",
            safety_status="blocked",
            reason_code="output_projection_contract_failed",
            answer="生成的查询未通过输出合同校验。",
            sql=sql,
            tool_calls=(resolved_call,) if resolved_call else (),
            trace_steps=tuple(trace_steps),
            blocked_reason="生成的查询未通过输出合同校验。",
            error_type="output_projection_contract_failed",
            langfuse_trace_id=lifecycle.get("trace_id"),
            langfuse_trace_url=lifecycle.get("trace_url"),
            langfuse_write_status=lifecycle.get("write_status") or "skipped",
            langfuse_span_mode=lifecycle.get("span_mode") or "post_hoc",
        )

    # 步骤 2：provider / plan / DB 出错是技术问题，safety 必须保持 passed。-----------------
    if result is None or resolved_error is not None or result.safety_status != "passed":
        execution = "external_unavailable" if resolved_error in {"llm_generation_error", "query_plan_extraction_error"} else "failed"
        technical_message = message or (result.blocked_reason if result else None) or "Text2SQL 当前不可用。"
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status=execution,
            answer_status="no_answer",
            safety_status="passed",
            reason_code=resolved_error or "text2sql_failed",
            answer="当前无法完成数据查询，请稍后再试。",
            sql=sql,
            tables_used=tuple(result.tables_used) if result else (),
            tool_calls=(resolved_call,) if resolved_call else (),
            trace_steps=tuple(trace_steps),
            diagnostics={"technical_message": technical_message},
            error_type=resolved_error or "text2sql_failed",
            sql_time_ms=result.sql_time_ms if result else 0.0,
            langfuse_trace_id=lifecycle.get("trace_id"),
            langfuse_trace_url=lifecycle.get("trace_url"),
            langfuse_write_status=lifecycle.get("write_status") or "skipped",
            langfuse_span_mode=lifecycle.get("span_mode") or "post_hoc",
        )

    # 步骤 3：只有 Guard 已通过且数据库执行成功，才允许构造 typed SQL Evidence。------------
    if not sql:
        raise ValueError("SQL 成功结果不能缺 guarded SQL")
    fingerprint = _result_fingerprint(result.columns, result.rows)
    evidence = make_sql_evidence(
        run_id=request.run_id,
        guarded_sql=sql,
        columns=tuple(result.columns),
        rows_count=len(result.rows),
        result_fingerprint=fingerprint,
        queried_at=datetime.now(UTC).isoformat(),
        database_identity="sqlalchemy-session",
        runtime_identity="text2sql-pipeline-v1" if request.force_new_pipeline else "text2sql-legacy-v1",
        safe_result_view=tuple(tuple(row.get(column) for column in result.columns) for row in result.rows),
    )
    ledger = EvidenceLedger.from_candidates(run_id=request.run_id, evidence=(evidence,))
    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="selected")
    ledger = ledger.transition(evidence_ids=(evidence.ref.evidence_id,), to_stage="generation_visible")
    answer = _build_answer(answer_hint, result.rows)
    diagnostics: dict[str, Any] = {"result_fingerprint": fingerprint}
    if request.follow_up_context is not None:
        diagnostics["evidence_validity"] = {
            "runtime_kind": "not_applicable",
            "requirement_equivalent": False,
            "decision": "reacquired",
            "reason": "sql_has_no_snapshot",
            "old_new_relation": "changed" if any(
                ref.content_identity != fingerprint for ref in request.follow_up_context.old_evidence_refs
            ) else "unchanged_but_fresh_query",
        }
    return ToolObservation(
        tool_name="text2sql",
        route="sql",
        execution_status="completed",
        answer_status="complete",
        safety_status="passed",
        reason_code="sql_completed",
        answer=answer,
        sql=sql,
        columns=tuple(result.columns),
        rows=tuple(result.rows),
        tables_used=tuple(result.tables_used),
        chart_spec=chart_spec or build_chart_spec(columns=result.columns, rows=result.rows, question=request.question),
        tool_calls=(resolved_call,) if resolved_call else (),
        trace_steps=tuple(trace_steps),
        evidence_refs=(evidence.ref.audit_projection(),),
        ledger_projection=ledger.safe_projection(),
        evidence_ledger=ledger,
        raw_evidence=(evidence,),
        diagnostics=diagnostics,
        sql_time_ms=result.sql_time_ms,
        langfuse_trace_id=lifecycle.get("trace_id"),
        langfuse_trace_url=lifecycle.get("trace_url"),
        langfuse_write_status=lifecycle.get("write_status") or "skipped",
        langfuse_span_mode=lifecycle.get("span_mode") or "post_hoc",
    )


def _build_answer(answer_hint: str, rows: list[dict[str, Any]]) -> str:
    """保留 M5 的 SQL 兼容话术；Harness 不重写已验证的表格结果。"""

    if not rows:
        return f"{answer_hint}：暂无数据。"
    first_row = "，".join(f"{key}={value}" for key, value in rows[0].items())
    return f"{answer_hint}：{first_row}（共 {len(rows)} 行结果）"


class Text2SQLToolAdapter:
    """把新/legacy Text2SQL 封装成一个深 Tool；`force_new_pipeline` 不再绕过 Harness。"""

    def __init__(self, *, db: Session, schema_vector_index: Any | None = None) -> None:
        self._db = db
        self._schema_vector_index = schema_vector_index

    def run(self, request: HarnessRequest) -> ToolObservation:
        """执行选定 pipeline，并把其旧错误形状翻译为 M35 四轴。"""

        if request.caller is None or request.active_sql_role is None:
            raise ValueError("未解析 caller 不得进入 Text2SQL Tool")
        if request.active_sql_role not in request.caller.resolved_roles:
            raise ValueError("active SQL role 不属于 trusted caller")
        if request.force_new_pipeline:
            return self._run_new_pipeline(request)
        return self._run_legacy_pipeline(request)

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        """Hybrid SQL branch 复用原 Tool；private Evidence 由 `_sql_observation` 单点构造。"""

        return self.run(request)

    def _run_new_pipeline(self, request: HarnessRequest) -> ToolObservation:
        """复用既有 Schema Retrieval → QueryPlan → Guard 深链。"""

        result: Text2SQLPipelineResult = run_text2sql_pipeline(
            question=request.question,
            user_role=request.active_sql_role or "",
            db=self._db,
            trace_id=request.run_id,
            schema_retrieval_profile=request.schema_retrieval_profile,
            schema_fusion_strategy=request.schema_fusion_strategy,
            schema_vector_index=self._schema_vector_index,
        )
        semantic_request_rejection = any(
            step.name == "plan_validation"
            and step.metadata.get("blocked_via") == "semantic_request_validation"
            for step in result.trace_steps
        )
        output_projection_rejection = result.error_type == "output_projection_contract_failed"
        return _sql_observation(
            request=request,
            sql=result.sql,
            answer_hint=result.answer_hint,
            tool_result=result.tool_result,
            error_type=result.error_type,
            message=result.blocked_reason,
            tool_call=result.tool_call,
            trace_steps=tuple(result.trace_steps),
            chart_spec=result.chart_spec,
            lifecycle={
                "trace_id": result.langfuse_trace_id,
                "trace_url": result.langfuse_trace_url,
                "write_status": result.langfuse_write_status,
                "span_mode": result.langfuse_span_mode,
            },
            semantic_request_rejection=semantic_request_rejection,
            output_projection_rejection=output_projection_rejection,
        )

    def _run_legacy_pipeline(self, request: HarnessRequest) -> ToolObservation:
        """保留旧 baseline 的诊断价值，但仍把它收进同一个 Tool adapter。"""

        started_at = perf_counter()
        if looks_like_dangerous_sql(request.question) and match_template(request.question) is None:
            guard = validate_readonly_sql(request.question)
            if not guard.is_allowed:
                return _sql_observation(
                    request=request,
                    sql=request.question,
                    answer_hint="legacy SQL 查询结果",
                    tool_result=None,
                    error_type="sql_guard_blocked",
                    message=guard.blocked_reason,
                )
        matched = match_template(request.question)
        try:
            if matched is not None:
                sql, parameters, answer_hint = matched.sql, matched.parameters, matched.answer_hint
            else:
                generated = generate_sql(
                    question=request.question,
                    user_role=request.active_sql_role or "",
                    domain_schema=load_domain_schema(),
                )
                sql, parameters, answer_hint = generated.sql, {}, "LLM SQL 查询结果"
        except LLMGenerationError as exc:
            return _sql_observation(
                request=request,
                sql=None,
                answer_hint="legacy SQL 查询结果",
                tool_result=None,
                error_type="llm_generation_error",
                message=str(exc),
                tool_call=ToolCallTrace(
                    tool_name="llm_sql_generator", status="error", latency_ms=round((perf_counter() - started_at) * 1000, 3),
                    error_type="llm_generation_error", message=str(exc),
                ),
            )
        result = run_sql_tool(
            db=self._db,
            sql=sql,
            parameters=parameters,
            user_role=request.active_sql_role or "",
            trace_id=request.run_id,
            domain_schema=load_domain_schema(),
        )
        return _sql_observation(
            request=request,
            sql=sql,
            answer_hint=answer_hint,
            tool_result=result,
            error_type=result.error_type,
            message=result.blocked_reason,
        )


class RAGToolAdapter:
    """只调用 `RAGAnswerFlow.run()`；含 M37 runtime 隔离但不泄露 RAG 内部控制。"""

    def __init__(
        self,
        *,
        answer_flow: RAGAnswerFlow | None = None,
        knowledge_runtime_kind: Literal["business_release", "external_profile"] = "business_release",
    ) -> None:
        self._answer_flow = answer_flow or RAGAnswerFlow()
        self._knowledge_runtime_kind = knowledge_runtime_kind

    def run(self, request: HarnessRequest) -> ToolObservation:
        """把已经闭合的 AnswerFlow 四轴结果原样映射到 ToolObservation。"""

        if request.caller is None:
            raise ValueError("未解析 caller 不得进入 RAG Tool")
        follow_up = request.follow_up_context
        if (
            follow_up is not None
            and follow_up.knowledge_runtime_kind != self._knowledge_runtime_kind
        ):
            raise ValueError("follow-up knowledge runtime 与旧 Evidence 不一致")
        requirement = (
            follow_up.current_requirement
            if follow_up is not None and follow_up.current_requirement is not None
            else AnswerEvidenceRequirement()
        )
        result = self._answer_flow.run(
            RAGAnswerRequest(
                question=request.question,
                caller=request.caller,
                run_id=request.run_id,
                requirement=requirement,
                knowledge_runtime_kind=self._knowledge_runtime_kind,
                prior_evidence_refs=follow_up.old_evidence_refs if follow_up is not None else (),
                requirement_equivalent=follow_up.requirement_equivalent if follow_up is not None else False,
            )
        )
        safe = result.safe_projection()
        diagnostics = dict(safe["diagnostics"])
        diagnostics["knowledge_runtime_kind"] = self._knowledge_runtime_kind
        validity = dict(safe["evidence_validity"])
        if follow_up is not None:
            validity["previous_requirement_identity"] = (
                follow_up.previous_requirement.identity if follow_up.previous_requirement else None
            )
            validity["current_requirement_identity"] = (
                follow_up.current_requirement.identity if follow_up.current_requirement else None
            )
        diagnostics["evidence_validity"] = validity
        status = "success" if result.execution_status == "completed" and result.safety_status == "passed" else (
            "blocked" if result.safety_status == "blocked" else "error"
        )
        tool_call = ToolCallTrace(
            tool_name="rag_answer_flow",
            status=status,
            latency_ms=result.diagnostics.elapsed_ms,
            error_type=None if status == "success" else result.reason_code,
        )
        return ToolObservation(
            tool_name="rag_answer_flow",
            route="rag",
            execution_status=result.execution_status,
            answer_status=result.answer_status,
            safety_status=result.safety_status,
            reason_code=result.reason_code,
            answer=result.answer,
            citations=tuple(safe["citations"]),
            docs_used=tuple(safe["docs_used"]),
            tool_calls=(tool_call,),
            evidence_refs=tuple(item["ref"] for item in safe["ledger"]["evidence"]),
            ledger_projection=safe["ledger"],
            diagnostics=diagnostics,
            blocked_reason=("当前身份无权访问相关文档。" if result.safety_status == "blocked" else None),
            error_type=None if result.safety_status == "passed" else result.reason_code,
        )

    def run_for_hybrid(self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement) -> ToolObservation:
        """只运行 RAG 取证与 Gate，把已授权 Document Evidence 留在 Harness 私有边界。"""

        if request.caller is None:
            raise ValueError("未解析 caller 不得进入 RAG Tool")
        prepared = self._answer_flow.prepare_for_hybrid(
            RAGAnswerRequest(
                question=request.question,
                caller=request.caller,
                run_id=request.run_id,
                requirement=requirement,
                knowledge_runtime_kind=self._knowledge_runtime_kind,
            )
        )
        if not prepared.available:
            failed = prepared.result
            if failed is None:
                raise ValueError("Hybrid RAG Gate 未返回闭合失败结果")
            safe = failed.safe_projection()
            diagnostics = dict(safe["diagnostics"])
            diagnostics["knowledge_runtime_kind"] = self._knowledge_runtime_kind
            diagnostics["hybrid_rag_mode"] = "evidence_gate_only"
            return ToolObservation(
                tool_name="rag_evidence_gate",
                route="rag",
                execution_status=failed.execution_status,
                answer_status=failed.answer_status,
                safety_status=failed.safety_status,
                reason_code=failed.reason_code,
                tool_calls=(
                    ToolCallTrace(
                        tool_name="rag_evidence_gate",
                        status="blocked" if failed.safety_status == "blocked" else "error",
                        latency_ms=failed.diagnostics.elapsed_ms,
                        error_type=failed.reason_code,
                    ),
                ),
                diagnostics=diagnostics,
                error_type=failed.reason_code if failed.execution_status != "completed" else None,
                blocked_reason=("文档证据未获授权。" if failed.safety_status == "blocked" else None),
            )

        gate = prepared.gate
        if gate is None or gate.context is None:
            raise ValueError("Hybrid RAG Gate 成功结果缺少 context")
        evidence = gate.context.evidence
        return ToolObservation(
            tool_name="rag_evidence_gate",
            route="rag",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="hybrid_document_evidence_ready",
            tool_calls=(
                ToolCallTrace(
                    tool_name="rag_evidence_gate",
                    status="success",
                    latency_ms=prepared.diagnostics.elapsed_ms,
                ),
            ),
            evidence_refs=tuple(item.ref.audit_projection() for item in evidence),
            ledger_projection=gate.ledger.safe_projection(),
            evidence_ledger=gate.ledger,
            raw_evidence=evidence,
            diagnostics={
                **prepared.diagnostics.safe_projection(),
                "knowledge_runtime_kind": self._knowledge_runtime_kind,
                "hybrid_rag_mode": "evidence_gate_only",
            },
        )
