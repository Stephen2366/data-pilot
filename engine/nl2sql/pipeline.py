"""M11 single-step Text2SQL pipeline 编排。

这条新链路把 M9 Schema Retrieval、M10 QueryPlanStep 和 M5 SQL Tool 串起来。它刻意保持为
普通 Python 函数，而不是引入 LangGraph / DB-GPT AWEL：Phase 3A 要验证的是中间层结构和
trace 可观测性，不是重开一个运行时平台。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.agent import ToolCallTrace
from engine.nl2sql.generator import (
    LLMGenerationError,
    QueryPlanExtractionError,
    generate_query_plan,
    generate_sql_from_plan_step,
    get_default_llm_client,
)
from engine.nl2sql.planner import QueryPlan, validate_query_plan
from engine.nl2sql.schema_loader import DomainSchema, load_domain_schema
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.objects import SchemaGraph, SchemaRetrievalResult
from engine.schema_retrieval.retriever import retrieve_schema
from engine.tools.chart_tool import build_chart_spec
from engine.tools.sql_tool import SQLToolResult, run_sql_tool
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

    @property
    def safety_status(self) -> str:
        """把 pipeline 结果压成响应层容易判断的安全状态。"""

        if self.tool_result is not None:
            return self.tool_result.safety_status
        return "blocked" if self.blocked_reason else "passed"


def _elapsed_ms(started_at: float) -> float:
    """返回保留 3 位小数的毫秒耗时。"""

    return round((perf_counter() - started_at) * 1000, 3)


def _step(
    *,
    name: str,
    step_index: int,
    step_type: str | None = None,
    status: str = "success",
    started_at: float,
    input_summary: str = "",
    output_summary: str = "",
    error_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    parent_step_id: str | None = None,
) -> TraceStep:
    """创建一条 TraceStep，统一耗时和字段默认值。"""

    return TraceStep(
        name=name,
        step_index=step_index,
        step_type=step_type or name,
        status=status,
        input_summary=input_summary,
        output_summary=output_summary,
        latency_ms=_elapsed_ms(started_at),
        error_type=error_type,
        metadata=metadata or {},
        parent_step_id=parent_step_id,
    )


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


def _retrieval_metadata(retrieval_result: SchemaRetrievalResult) -> dict[str, Any]:
    """把检索详情压成 JSONL 友好的诊断摘要。"""

    metric_doc_hits = [
        hit.document.doc_id
        for hit in retrieval_result.merged_hits
        if hit.doc_type == "metric_doc"
    ]
    return {
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
) -> Text2SQLPipelineResult:
    """执行 M11 single-step Text2SQL pipeline。

    ★ 处理顺序与 trace step 顺序保持一致；任何一步失败都返回结构化 blocked 结果，不降级到
    全量 schema prompt、模板 SQL 或 SQL 自动修复。
    """

    active_domain_schema = domain_schema or load_domain_schema()
    trace_steps: list[TraceStep] = []
    step_index = 1
    answer_hint = "新 Text2SQL 查询结果"
    llm_client = get_default_llm_client()

    # 步骤 1：Schema Retrieval ==============================================================
    started_at = perf_counter()
    retrieval_result = retrieve_schema(
        question=question,
        user_role=user_role,
        top_k=top_k,
        domain_schema=active_domain_schema,
    )
    trace_steps.append(
        _step(
            name="schema_retrieval",
            step_index=step_index,
            started_at=started_at,
            input_summary=question,
            output_summary=f"merged_hits={len(retrieval_result.merged_hits)}",
            metadata=_retrieval_metadata(retrieval_result),
        )
    )
    step_index += 1
    if not retrieval_result.merged_hits:
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=["insufficient_schema_context"],
            blocked_reason="Schema Retrieval 未召回可用上下文。",
            error_type="insufficient_schema_context",
        )

    # 步骤 2：构建局部 SchemaGraph -----------------------------------------------------------
    started_at = perf_counter()
    schema_graph = build_schema_graph(retrieval_result.merged_hits, domain_schema=active_domain_schema)
    trace_steps.append(
        _step(
            name="schema_context",
            step_index=step_index,
            started_at=started_at,
            output_summary=f"tables={len(schema_graph.tables)}, fields={sum(len(v) for v in schema_graph.fields.values())}",
            metadata=_schema_graph_metadata(schema_graph),
        )
    )
    step_index += 1

    started_at = perf_counter()
    trace_steps.append(
        _step(
            name="join_path",
            step_index=step_index,
            started_at=started_at,
            output_summary=f"join_paths={len(schema_graph.join_paths)}",
            metadata=_join_path_metadata(schema_graph),
        )
    )
    step_index += 1

    # 步骤 3：QueryPlan 生成与自检 -----------------------------------------------------------
    started_at = perf_counter()
    try:
        plan = generate_query_plan(
            question=question,
            schema_graph=schema_graph,
            domain_schema=active_domain_schema,
            llm_client=llm_client,
        )
    except QueryPlanExtractionError as exc:
        trace_steps.append(
            _step(
                name="query_plan",
                step_index=step_index,
                status="error",
                started_at=started_at,
                error_type=exc.issue_tag,
                output_summary=str(exc),
            )
        )
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=[exc.issue_tag],
            blocked_reason=f"QueryPlan 生成失败：{exc}",
            error_type=exc.issue_tag,
        )
    except LLMGenerationError as exc:
        trace_steps.append(
            _step(
                name="query_plan",
                step_index=step_index,
                status="error",
                started_at=started_at,
                error_type="llm_generation_error",
                output_summary=str(exc),
            )
        )
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=["llm_generation_error"],
            blocked_reason=f"QueryPlan 生成失败：{exc}",
            error_type="llm_generation_error",
        )

    trace_steps.append(
        _step(
            name="query_plan",
            step_index=step_index,
            started_at=started_at,
            output_summary=plan.to_human_explanation(),
            metadata={
                "step_count": len(plan.steps),
                "sql_step_count": sum(1 for step in plan.steps if step.step_type == "sql_query"),
                "step_ids": [step.step_id for step in plan.steps],
            },
        )
    )
    step_index += 1

    started_at = perf_counter()
    validation = validate_query_plan(
        plan,
        schema_graph=schema_graph,
        domain_schema=active_domain_schema,
        user_role=user_role,
    )
    trace_steps.append(
        _step(
            name="plan_validation",
            step_index=step_index,
            status="success" if validation.is_valid else "blocked",
            started_at=started_at,
            output_summary="valid" if validation.is_valid else "; ".join(validation.errors),
            error_type=None if validation.is_valid else "plan_validation_failed",
            metadata={"issue_tags": validation.issue_tags, "errors": validation.errors},
        )
    )
    step_index += 1
    if not validation.is_valid:
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=validation.issue_tags,
            blocked_reason="QueryPlan 自检未通过：" + "；".join(validation.errors),
            error_type="plan_validation_failed",
        )

    plan_step = _first_sql_step(plan)
    if plan_step is None:
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=["invalid_query_plan"],
            blocked_reason="QueryPlan 缺少可执行 sql_query step。",
            error_type="invalid_query_plan",
        )

    # 步骤 4：局部 Schema SQL 生成 -----------------------------------------------------------
    started_at = perf_counter()
    try:
        generated_sql = generate_sql_from_plan_step(
            question=question,
            user_role=user_role,
            plan_step=plan_step,
            schema_graph=schema_graph,
            domain_schema=active_domain_schema,
            llm_client=llm_client,
        )
    except LLMGenerationError as exc:
        trace_steps.append(
            _step(
                name="sql_generation",
                step_index=step_index,
                status="error",
                started_at=started_at,
                error_type="llm_generation_error",
                output_summary=str(exc),
                parent_step_id=plan_step.step_id,
            )
        )
        return _blocked_result(
            sql=None,
            answer_hint=answer_hint,
            trace_steps=trace_steps,
            issue_tags=["llm_generation_error"],
            blocked_reason=f"局部 Schema SQL 生成失败：{exc}",
            error_type="llm_generation_error",
        )

    trace_steps.append(
        _step(
            name="sql_generation",
            step_index=step_index,
            started_at=started_at,
            output_summary=generated_sql.reasoning_summary,
            metadata={
                "tables_used": generated_sql.tables_used,
                "confidence": generated_sql.confidence,
                "sql_preview": generated_sql.sql[:300],
                "plan_step_tables": plan_step.tables,
                "plan_step_columns": plan_step.columns,
                "plan_step_filters": plan_step.filters,
                "plan_step_metrics": plan_step.metrics,
                "plan_step_joins": plan_step.joins,
                "plan_step_output_columns": plan_step.output_columns,
            },
            parent_step_id=plan_step.step_id,
        )
    )
    step_index += 1

    # 步骤 5：SQL Guard + SQL 执行 -----------------------------------------------------------
    tool_result = run_sql_tool(
        db=db,
        sql=generated_sql.sql,
        parameters={},
        user_role=user_role,
        trace_id=trace_id,
        domain_schema=active_domain_schema,
    )
    guard_status = "success" if tool_result.safety_status == "passed" else "blocked"
    trace_steps.append(
        TraceStep(
            name="sql_guard",
            step_index=step_index,
            step_type="sql_guard",
            status=guard_status,
            input_summary="validate generated SQL",
            output_summary=tool_result.blocked_reason or "SQL Guard passed",
            latency_ms=tool_result.tool_call.latency_ms if tool_result.tool_call else 0.0,
            error_type=tool_result.error_type if tool_result.safety_status != "passed" else None,
            metadata={"tables_used": tool_result.tables_used, "blocked_reason": tool_result.blocked_reason},
            parent_step_id=plan_step.step_id,
        )
    )
    step_index += 1

    if tool_result.safety_status != "passed":
        return Text2SQLPipelineResult(
            sql=generated_sql.sql,
            answer_hint=answer_hint,
            tool_result=tool_result,
            trace_steps=trace_steps,
            issue_tags=[tool_result.error_type or "sql_guard_blocked"],
            blocked_reason=tool_result.blocked_reason,
            error_type=tool_result.error_type,
            tool_call=tool_result.tool_call,
        )

    trace_steps.append(
        TraceStep(
            name="sql_execution",
            step_index=step_index,
            step_type="sql_query",
            status="success",
            input_summary="execute generated SQL",
            output_summary=_sql_execution_summary(tool_result),
            latency_ms=tool_result.sql_time_ms,
            metadata={
                "row_count": len(tool_result.rows),
                "column_count": len(tool_result.columns),
                "latency_ms": tool_result.sql_time_ms,
                "tables_used": tool_result.tables_used,
            },
            parent_step_id=plan_step.step_id,
        )
    )
    step_index += 1

    # 步骤 6：图表决策只做附加观察，不影响 SQL 答案。-----------------------------------------
    started_at = perf_counter()
    chart_spec = build_chart_spec(columns=tool_result.columns, rows=tool_result.rows, question=question)
    trace_steps.append(
        _step(
            name="chart_decision",
            step_index=step_index,
            step_type="chart_decision",
            status="success" if chart_spec else "skipped",
            started_at=started_at,
            output_summary=f"chart_mark={chart_spec.get('mark')}" if chart_spec else "no chart",
            metadata={"has_chart": chart_spec is not None, "mark": chart_spec.get("mark") if chart_spec else None},
        )
    )

    return Text2SQLPipelineResult(
        sql=generated_sql.sql,
        answer_hint=answer_hint,
        tool_result=tool_result,
        trace_steps=trace_steps,
        chart_spec=chart_spec,
    )
