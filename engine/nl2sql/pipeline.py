"""M11 single-step Text2SQL pipeline 编排。

这条新链路把 M9 Schema Retrieval、M10 QueryPlanStep 和 M5 SQL Tool 串起来。它刻意保持为
普通 Python 函数，而不是引入 LangGraph / DB-GPT AWEL：Phase 3A 要验证的是中间层结构和
trace 可观测性，不是重开一个运行时平台。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.agent import ToolCallTrace
from engine.nl2sql.generator import (
    LLMGenerationError,
    QueryPlanExtractionError,
    SQLPlanContractError,
    generate_query_plan,
    generate_sql_from_plan_step,
    get_default_llm_client,
    validate_sql_plan_contract,
)
from engine.nl2sql.llm_call import LLMCallEvidence
from engine.nl2sql.planner import QueryPlan, validate_query_plan
from engine.nl2sql.semantic_validation import validate_request_semantics
from engine.nl2sql.schema_loader import DomainSchema, load_domain_schema
from engine.nl2sql.sql_repair import (
    SQLRepairSnapshot,
    SQLRepairStrategy,
    repair_sql_candidate,
    validate_sql_repair_strategy,
)
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.objects import SchemaGraph, SchemaRetrievalResult
from engine.schema_retrieval.retriever import retrieve_schema
from engine.schema_retrieval.vector_index import VectorIndex
from engine.sql_guard.guard import validate_readonly_sql
from engine.sql_guard.policy import validate_sql_policy
from engine.sql_guard.precheck import looks_like_dangerous_sql
from engine.tools.chart_tool import build_chart_spec
from engine.tools.sql_tool import SQLToolResult, run_sql_tool
from engine.trace.lifecycle import TraceContext, TraceLifecycleSnapshot, build_trace_context
from engine.trace.recorder import TraceStep


@dataclass(frozen=True)
class Text2SQLPipelineResult:
    """Text2SQL pipeline 的出站返回包，只向上交付给 `/api/query` API 层。

    设计意图 —— 把「业务响应格式」和「引擎执行结果」拆开：
    ------------------------------------------------------------------
    1. pipeline 是引擎层，关心的是 SQL 生成、执行、安全拦截、trace 记录；
    2. API 层关心的是用户看到的 AgentResponse（type / message / data / tool_call 等），
        包括统一话术包装、可视化图表注入、错误码映射；
    3. 如果 pipeline 自己拼 AgentResponse，M11 的每个分支都要复制一套响应契约，
        后续改话术或改字段会同时污染引擎层和 API 层。

    所以 Text2SQLPipelineResult 只携带「事实」：生成的 SQL、执行结果、trace 步骤、
    问题标签、拦截原因、错误类型、图表规格。API 层拿到后统一翻译成 AgentResponse。

    ★ 安全状态汇总：safety_status 属性会把 tool_result.safety_status 透传出来；
        没有 tool_result 时，只要存在 blocked_reason 就视为 blocked，否则 passed。
        API 层用这一个字段即可决定是返回正常数据、友好拒绝还是错误提示。
    """

    sql: str | None
    answer_hint: str
    tool_result: SQLToolResult | None
    trace_steps: list[TraceStep]
    issue_tags: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    error_type: str | None = None
    tool_call: ToolCallTrace | None = None
    chart_spec: dict[str, Any] | None = None
    langfuse_trace_id: str | None = None
    langfuse_trace_url: str | None = None
    langfuse_write_status: str = "skipped"
    langfuse_span_mode: str = "post_hoc"
    # 只交给同进程 Agent Loop 的 repair action；API/JSONL projector 没有读取入口。
    repair_snapshot: SQLRepairSnapshot | None = field(default=None, repr=False, compare=False)

    @property
    def safety_status(self) -> str:
        """把 pipeline 结果压成响应层容易判断的安全状态。"""

        if self.tool_result is not None:
            return self.tool_result.safety_status
        return "blocked" if self.blocked_reason else "passed"


# 兼容既有 import 名称；实际语义已收紧为“原计划 + candidate + typed issue”不可变快照。
SQLRepairContext = SQLRepairSnapshot


def _blocked_result(
    *,
    sql: str | None,
    answer_hint: str,
    trace_steps: list[TraceStep],
    issue_tags: list[str],
    blocked_reason: str,
    error_type: str,
    tool_call: ToolCallTrace | None = None,
) -> Text2SQLPipelineResult:
    """构造 pipeline 内部拦截结果，供 API 层统一转成 blocked AgentResponse。"""

    resolved_tool_call = tool_call or ToolCallTrace(
        tool_name="text2sql_pipeline",
        status="blocked" if error_type != "llm_generation_error" else "error",
        latency_ms=0.0,
        sql=sql,
        error_type=error_type,
        message=blocked_reason,
    )
    return Text2SQLPipelineResult(
        sql=sql,
        answer_hint=answer_hint,
        tool_result=None,
        trace_steps=trace_steps,
        issue_tags=issue_tags,
        blocked_reason=blocked_reason,
        error_type=error_type,
        tool_call=resolved_tool_call,
    )


def _with_trace_snapshot(
    result: Text2SQLPipelineResult,
    trace_context: TraceContext,
) -> Text2SQLPipelineResult:
    """把 lifecycle 最终状态合并进 pipeline result。

    `snapshot()` 会 flush LangFuse live writer；所有 return 分支都走这里，避免成功/拦截/异常路径
    写出的 JSONL 映射字段不一致。
    """

    snapshot: TraceLifecycleSnapshot = trace_context.snapshot(
        status=result.safety_status,
        output_summary=result.blocked_reason or result.answer_hint,
        error_type=result.error_type,
    )
    return replace(
        result,
        trace_steps=snapshot.trace_steps,
        langfuse_trace_id=snapshot.langfuse_trace_id,
        langfuse_trace_url=snapshot.langfuse_trace_url,
        langfuse_write_status=snapshot.langfuse_write_status,
        langfuse_span_mode=snapshot.langfuse_span_mode,
    )


def _retrieval_metadata(
    retrieval_result: SchemaRetrievalResult,
    *,
    schema_retrieval_profile: str = "default",
    fusion_strategy: str = "weighted",
) -> dict[str, Any]:
    """把检索详情压成 JSONL 友好的诊断摘要。"""

    metric_doc_hits = [
        hit.document.doc_id
        for hit in retrieval_result.merged_hits
        if hit.doc_type == "metric_doc"
    ]
    return {
        "schema_retrieval_profile": schema_retrieval_profile,
        "fusion_strategy": fusion_strategy,
        "keyword_hit_count": len(retrieval_result.keyword_hits),
        "vector_hit_count": len(retrieval_result.vector_hits),
        "merged_hit_count": len(retrieval_result.merged_hits),
        "top_doc_ids": [hit.document.doc_id for hit in retrieval_result.merged_hits[:10]],
        "top_doc_types": [hit.doc_type for hit in retrieval_result.merged_hits[:10]],
        "metric_doc_hits": metric_doc_hits,
    }


def _schema_graph_metadata(schema_graph: SchemaGraph) -> dict[str, Any]:
    """统计局部 SchemaGraph 的表、字段和指标规模。"""

    return {
        "tables": schema_graph.tables,
        # Context Contract 需要的是局部 SchemaGraph 的真实字段，不是最终 SELECT 的返回列。
        "fields": [f"{table}.{column}" for table, columns in schema_graph.fields.items() for column in columns],
        "table_count": len(schema_graph.tables),
        "field_count": sum(len(columns) for columns in schema_graph.fields.values()),
        "metrics": schema_graph.metrics,
        "metric_count": len(schema_graph.metrics),
    }


def _join_path_metadata(schema_graph: SchemaGraph) -> dict[str, Any]:
    """提取 JoinPath 的 relation id，便于 M12 对照报告复用。"""

    relation_ids = [edge.relation_id for join_path in schema_graph.join_paths for edge in join_path.edges]
    return {
        "join_path_count": len(schema_graph.join_paths),
        "relation_ids": relation_ids,
        "relations": [relation.get("id") for relation in schema_graph.relations],
    }


def _llm_error_metadata(exc: LLMGenerationError) -> dict[str, Any]:
    """把 LLM 失败上下文压成 trace metadata，避免报告里只剩一句错误文案。"""

    metadata: dict[str, Any] = {}
    if exc.stage:
        metadata["stage"] = exc.stage
    if exc.raw_response_preview:
        metadata["raw_response_preview"] = exc.raw_response_preview
    if exc.parse_error:
        metadata["parse_error"] = exc.parse_error
    if exc.prompt_length is not None:
        metadata["prompt_length"] = exc.prompt_length
    if exc.error_subtype:
        metadata["error_subtype"] = exc.error_subtype
    if exc.call_evidence is not None:
        metadata["llm_call"] = exc.call_evidence.to_trace_metadata()
    return metadata


def _llm_success_metadata(evidence: list[LLMCallEvidence]) -> dict[str, Any]:
    """成功路径也写 attempt 证据，避免报告只能看见失败调用。"""

    return {"llm_call": evidence[-1].to_trace_metadata()} if evidence else {}


def _first_sql_step(plan: QueryPlan):
    """取出 Phase 3A 允许执行的唯一 sql_query step。"""

    for step in plan.steps:
        if step.step_type == "sql_query":
            return step
    return None


def _sql_execution_summary(tool_result: SQLToolResult) -> str:
    """把 SQL 执行结果压成人能快速理解的一句话。"""

    if not tool_result.rows:
        return "暂无数据。"
    first_row = tool_result.rows[0]
    first_row_summary = "，".join(f"{key}={value}" for key, value in first_row.items())
    return f"首行：{first_row_summary}（共 {len(tool_result.rows)} 行结果）"


def run_text2sql_pipeline(
    *,
    question: str,
    user_role: str,
    db: Session,
    trace_id: str,
    domain_schema: DomainSchema | None = None,
    top_k: int = 30,
    schema_retrieval_profile: str = "default",
    schema_fusion_strategy: str = "weighted",
    schema_vector_index: VectorIndex | None = None,
    repair_context: SQLRepairContext | None = None,
    repair_strategy: SQLRepairStrategy = "deterministic_ast",
) -> Text2SQLPipelineResult:
    """执行 M11 single-step Text2SQL pipeline。

    ★ 处理顺序与 trace step 顺序保持一致；任何一步失败都返回结构化 blocked 结果，不降级到
    全量 schema prompt、模板 SQL 或 SQL 自动修复。
    """

    selected_repair_strategy = validate_sql_repair_strategy(repair_strategy)
    active_domain_schema = domain_schema or load_domain_schema()
    trace_context = build_trace_context(trace_id=trace_id, question=question, user_role=user_role)
    answer_hint = "新 Text2SQL 查询结果"

    # 步骤 0：用户原始输入危险 SQL 预检 ======================================================
    # ★ 这一步属于 pipeline 的统一安全边界，而不是 API 层临时拦截。否则 `DROP TABLE ...`
    # 会在进入 pipeline 前返回，JSONL / LangFuse 里看不到 `sql_guard` blocked span。
    if looks_like_dangerous_sql(question):
        span = trace_context.start_span(
            name="sql_guard",
            step_type="sql_guard",
            input_summary="validate raw user SQL-like input",
        )
        guard_result = validate_readonly_sql(question)
        if not guard_result.is_allowed:
            blocked_reason = guard_result.blocked_reason or "SQL Guard 已拦截。"
            span.end(
                status="blocked",
                output_summary=blocked_reason,
                error_type="sql_guard_blocked",
                metadata={"guard_stage": "raw_user_input", "blocked_reason": blocked_reason},
            )
            return _with_trace_snapshot(
                _blocked_result(
                    sql=question,
                    answer_hint=answer_hint,
                    trace_steps=trace_context.trace_steps,
                    issue_tags=["sql_guard_blocked"],
                    blocked_reason=blocked_reason,
                    error_type="sql_guard_blocked",
                    tool_call=ToolCallTrace(
                        tool_name="sql_guard",
                        status="blocked",
                        latency_ms=0.0,
                        sql=question,
                        error_type="sql_guard_blocked",
                        message=blocked_reason,
                    ),
                ),
                trace_context,
            )
        span.end(
            output_summary="raw input passed readonly precheck",
            metadata={"guard_stage": "raw_user_input"},
        )

    llm_client = get_default_llm_client()

    # 步骤 1：Schema Retrieval ==============================================================
    span = trace_context.start_span(name="schema_retrieval", input_summary=question)
    retrieval_result = retrieve_schema(
        question=question,
        user_role=user_role,
        top_k=top_k,
        domain_schema=active_domain_schema,
        schema_retrieval_profile=schema_retrieval_profile,
        fusion_strategy=schema_fusion_strategy,
        vector_index=schema_vector_index,
    )
    span.end(
        output_summary=f"merged_hits={len(retrieval_result.merged_hits)}",
        metadata=_retrieval_metadata(
            retrieval_result,
            schema_retrieval_profile=schema_retrieval_profile,
            fusion_strategy=schema_fusion_strategy,
        ),
    )
    if not retrieval_result.merged_hits:
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=["insufficient_schema_context"],
                blocked_reason="Schema Retrieval 未召回可用上下文。",
                error_type="insufficient_schema_context",
            ),
            trace_context,
        )

    # 步骤 2：构建局部 SchemaGraph -----------------------------------------------------------
    span = trace_context.start_span(name="schema_context")
    schema_graph = build_schema_graph(retrieval_result.merged_hits, domain_schema=active_domain_schema)
    span.end(
        output_summary=f"tables={len(schema_graph.tables)}, fields={sum(len(v) for v in schema_graph.fields.values())}",
        metadata=_schema_graph_metadata(schema_graph),
    )

    span = trace_context.start_span(name="join_path")
    span.end(
        output_summary=f"join_paths={len(schema_graph.join_paths)}",
        metadata=_join_path_metadata(schema_graph),
    )

    # 步骤 2.5：已知不支持需求的语义预检 -----------------------------------------------
    # ★ 这里不是用关键词替代 LLM，而是把已被 diagnostic 证明会“静默答错”的窄场景提前
    # 结构化拒绝。这样 trace / triage 能与真正的 LLM transport error 清楚区分。
    semantic_issue = validate_request_semantics(question, domain_schema=active_domain_schema)
    if semantic_issue is not None:
        span = trace_context.start_span(name="plan_validation", step_type="plan_validation")
        span.end(
            status="blocked",
            output_summary=semantic_issue.message,
            error_type="plan_validation_failed",
            metadata={
                "issue_tags": [semantic_issue.issue_tag],
                "errors": [semantic_issue.message],
                "blocked_via": semantic_issue.blocked_via,
            },
        )
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=[semantic_issue.issue_tag],
                blocked_reason="QueryPlan 语义预检未通过：" + semantic_issue.message,
                error_type="plan_validation_failed",
            ),
            trace_context,
        )

    # 步骤 3：QueryPlan 生成与自检 -----------------------------------------------------------
    span = trace_context.start_span(name="query_plan")
    query_plan_call_evidence: list[LLMCallEvidence] = []
    try:
        # ★ repair 的语义 authority 是首次已验证计划。这里仍用当前 SchemaGraph 重做本地
        # validator，但绝不再请求 provider 生成第二份 QueryPlan。
        plan = (
            QueryPlan(steps=[repair_context.plan_step])
            if repair_context is not None
            else generate_query_plan(
                question=question,
                schema_graph=schema_graph,
                domain_schema=active_domain_schema,
                llm_client=llm_client,
                llm_evidence_sink=query_plan_call_evidence.append,
            )
        )
    except QueryPlanExtractionError as exc:
        span.fail(
            error_type=exc.issue_tag,
            output_summary=str(exc),
            metadata=_llm_error_metadata(exc),
        )
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=[exc.issue_tag],
                blocked_reason=f"QueryPlan 生成失败：{exc}",
                error_type=exc.issue_tag,
            ),
            trace_context,
        )
    except LLMGenerationError as exc:
        span.fail(
            error_type="llm_generation_error",
            output_summary=str(exc),
            metadata=_llm_error_metadata(exc),
        )
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=["llm_generation_error"],
                blocked_reason=f"QueryPlan 生成失败：{exc}",
                error_type="llm_generation_error",
            ),
            trace_context,
        )

    span.end(
        output_summary=plan.to_human_explanation(),
        metadata={
            "step_count": len(plan.steps),
            "sql_step_count": sum(1 for step in plan.steps if step.step_type == "sql_query"),
            "step_ids": [step.step_id for step in plan.steps],
            # ★ M27 typed Plan / Join / Metric assertions 必须消费同一次执行证据。
            # 这里只写结构化计划字段，不保存 prompt 或 LLM 原文，因此 JSONL/audit 可以在
            # 不重跑模型的情况下复核“模型计划了哪些表、关系、指标和输出”。
            "plan_steps": [
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "tables": step.tables,
                    "columns": step.columns,
                    "metrics": step.metrics,
                    "joins": step.joins,
                    "group_by": step.group_by,
                    "order_by": step.order_by,
                    "output_columns": step.output_columns,
                }
                for step in plan.steps
            ],
            "repair_plan_reused": repair_context is not None,
            **_llm_success_metadata(query_plan_call_evidence),
        },
    )

    span = trace_context.start_span(name="plan_validation")
    validation = validate_query_plan(
        plan,
        schema_graph=schema_graph,
        domain_schema=active_domain_schema,
        user_role=user_role,
    )
    span.end(
        status="success" if validation.is_valid else "blocked",
        output_summary="valid" if validation.is_valid else "; ".join(validation.errors),
        error_type=None if validation.is_valid else "plan_validation_failed",
        metadata={"issue_tags": validation.issue_tags, "errors": validation.errors, "blocked_via": "query_plan_validation"},
    )
    if not validation.is_valid:
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=validation.issue_tags,
                blocked_reason="QueryPlan 自检未通过：" + "；".join(validation.errors),
                error_type="plan_validation_failed",
            ),
            trace_context,
        )

    plan_step = _first_sql_step(plan)
    if plan_step is None:
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=["invalid_query_plan"],
                blocked_reason="QueryPlan 缺少可执行 sql_query step。",
                error_type="invalid_query_plan",
            ),
            trace_context,
        )

    # 步骤 4：局部 Schema SQL 生成 -----------------------------------------------------------
    generation_stage = "sql_repair" if repair_context is not None else "sql_generation"
    span = trace_context.start_span(name=generation_stage, parent_step_id=plan_step.step_id)
    sql_call_evidence: list[LLMCallEvidence] = []
    try:
        generation_args = {
            "question": question,
            "user_role": user_role,
            "plan_step": plan_step,
            "schema_graph": schema_graph,
            "domain_schema": active_domain_schema,
            "llm_client": llm_client,
            "llm_evidence_sink": sql_call_evidence.append,
        }
        generated_sql = (
            repair_sql_candidate(
                **generation_args,
                candidate_sql=repair_context.candidate_sql,
                issue_code=repair_context.issue_code,
                strategy=selected_repair_strategy,
            )
            if repair_context is not None
            else generate_sql_from_plan_step(**generation_args)
        )
    except LLMGenerationError as exc:
        span.fail(
            error_type="llm_generation_error",
            output_summary=str(exc),
            metadata=_llm_error_metadata(exc),
        )
        return _with_trace_snapshot(
            _blocked_result(
                sql=None,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=["llm_generation_error"],
                blocked_reason=f"局部 Schema SQL {'修复' if repair_context else '生成'}失败：{exc}",
                error_type="llm_generation_error",
            ),
            trace_context,
        )

    # ★ 安全策略必须先于语义合同。这里做纯只读预检查；真正执行时 SQL Tool 仍会再验一次，
    # 形成 defense in depth，避免未来 caller 绕过 SQL Tool 的安全 seam。
    guard_precheck = validate_sql_policy(
        generated_sql.sql,
        user_role=user_role,
        domain_schema=active_domain_schema,
    )
    fidelity_result = None
    if guard_precheck.is_allowed:
        try:
            fidelity_result = validate_sql_plan_contract(
                generated_sql.sql,
                plan_step=plan_step,
                domain_schema=active_domain_schema,
                dialect="mysql",
            )
        except SQLPlanContractError as exc:
            span.fail(
                error_type=exc.issue_tag,
                output_summary=str(exc),
                metadata={
                    **_llm_error_metadata(exc),
                    **_llm_success_metadata(sql_call_evidence),
                    "generation_stage": generation_stage,
                    "repair_issue_code": repair_context.issue_code if repair_context else None,
                    "repair_strategy": selected_repair_strategy if repair_context else None,
                    "sql_guard_precheck_status": "passed",
                    "query_plan_step": plan_step.model_dump(mode="json"),
                    **exc.contract_result.to_trace_metadata(),
                },
            )
            return _with_trace_snapshot(
                _blocked_result(
                    sql=None,
                    answer_hint=answer_hint,
                    trace_steps=trace_context.trace_steps,
                    issue_tags=[exc.issue_tag, exc.contract_result.reason_code],
                    blocked_reason=f"SQL 未满足 QueryPlan 保真合同：{exc}",
                    error_type=exc.issue_tag,
                ),
                trace_context,
            )

    span.end(
        output_summary=generated_sql.reasoning_summary,
        metadata={
            **_llm_success_metadata(sql_call_evidence),
            "tables_used": generated_sql.tables_used,
            "confidence": generated_sql.confidence,
            "sql_preview": generated_sql.sql[:300],
            "plan_step_tables": plan_step.tables,
            "plan_step_columns": plan_step.columns,
            "plan_step_filters": plan_step.filters,
            "plan_step_metrics": plan_step.metrics,
            "plan_step_joins": plan_step.joins,
            "plan_step_output_columns": plan_step.output_columns,
            "query_plan_step": plan_step.model_dump(mode="json"),
            "generation_stage": generation_stage,
            "repair_issue_code": repair_context.issue_code if repair_context else None,
            "repair_strategy": selected_repair_strategy if repair_context else None,
            "sql_guard_precheck_status": "passed" if guard_precheck.is_allowed else "blocked",
            "sql_guard_precheck_reason": guard_precheck.blocked_reason,
            **(fidelity_result.to_trace_metadata() if fidelity_result is not None else {}),
        },
    )

    # 步骤 5：SQL Guard + SQL 执行 -----------------------------------------------------------
    tool_result = run_sql_tool(
        db=db,
        sql=generated_sql.sql,
        parameters={},
        user_role=user_role,
        trace_id=trace_id,
        domain_schema=active_domain_schema,
        trace_context=trace_context,
        trace_parent_step_id=plan_step.step_id,
    )

    if tool_result.safety_status != "passed":
        issued_repair_snapshot = (
            SQLRepairSnapshot(
                candidate_sql=generated_sql.sql,
                issue_code=tool_result.issue_code,
                plan_step=plan_step,
            )
            if repair_context is None and tool_result.issue_code == "mysql_unsupported_date_trunc"
            else None
        )
        return _with_trace_snapshot(
            Text2SQLPipelineResult(
                sql=generated_sql.sql,
                answer_hint=answer_hint,
                tool_result=tool_result,
                trace_steps=trace_context.trace_steps,
                issue_tags=[tool_result.error_type or "sql_guard_blocked"],
                blocked_reason=tool_result.blocked_reason,
                error_type=tool_result.error_type,
                tool_call=tool_result.tool_call,
                repair_snapshot=issued_repair_snapshot,
            ),
            trace_context,
        )

    # 步骤 6：核对真实 driver 返回的 body.columns，固定 API 表格 / chart 展示顺序。-----------
    output_span = trace_context.start_span(
        name="output_projection",
        step_type="output_contract",
        parent_step_id=plan_step.step_id,
    )
    expected_output = list(fidelity_result.planned_output_columns) if fidelity_result is not None else []
    if expected_output and tool_result.columns != expected_output:
        output_span.fail(
            error_type="output_projection_contract_failed",
            output_summary="SQL 执行结果列与 QueryPlan 展示顺序不一致。",
            metadata={
                "expected_columns": expected_output,
                "actual_columns": tool_result.columns,
                "reason_code": "body_columns_order_or_set_mismatch",
            },
        )
        return _with_trace_snapshot(
            _blocked_result(
                sql=generated_sql.sql,
                answer_hint=answer_hint,
                trace_steps=trace_context.trace_steps,
                issue_tags=["output_projection_contract_failed", "body_columns_order_or_set_mismatch"],
                blocked_reason="SQL 执行结果列未满足 QueryPlan 的精确投影与展示顺序。",
                error_type="output_projection_contract_failed",
                tool_call=tool_result.tool_call,
            ),
            trace_context,
        )
    output_span.end(
        output_summary="output projection matched",
        metadata={"expected_columns": expected_output, "actual_columns": tool_result.columns},
    )

    # 步骤 7：图表决策只做附加观察，不影响 SQL 答案。-----------------------------------------
    span = trace_context.start_span(name="chart_generation", step_type="chart_generation")
    chart_spec = build_chart_spec(columns=tool_result.columns, rows=tool_result.rows, question=question)
    span.end(
        status="success" if chart_spec else "skipped",
        output_summary=f"chart_mark={chart_spec.get('mark')}" if chart_spec else "no chart",
        metadata={"has_chart": chart_spec is not None, "mark": chart_spec.get("mark") if chart_spec else None},
    )

    return _with_trace_snapshot(
        Text2SQLPipelineResult(
            sql=generated_sql.sql,
            answer_hint=answer_hint,
            tool_result=tool_result,
            trace_steps=trace_context.trace_steps,
            chart_spec=chart_spec,
        ),
        trace_context,
    )
