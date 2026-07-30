"""M5 `/api/query`：自然语言问题 → SQL Tool → Trace + Chart + AgentResponse。

★ M4 仍然模板优先：M3 已验证过的高价值问题继续走稳定模板；模板未命中时才调用 LLM
生成 SQL。M5 在这条链路外层收口响应契约：SQL 执行进入 tool，结果进入 chart tool，
全过程写入 JSONL trace。
"""

from __future__ import annotations
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentResponse, CostInfo, QueryRequest, ToolCallTrace
from engine.nl2sql.generator import LLMGenerationError, generate_sql
from engine.nl2sql.pipeline import run_text2sql_pipeline
from engine.nl2sql.schema_loader import load_domain_schema
from engine.nl2sql.templates import match_template
from engine.sql_guard.guard import validate_readonly_sql
from engine.sql_guard.precheck import looks_like_dangerous_sql
from engine.tools.chart_tool import build_chart_spec
from engine.tools.sql_tool import SQLToolResult, run_sql_tool
from engine.trace.recorder import TraceRecord, TraceStep, append_trace


router = APIRouter(prefix="/api", tags=["query"])


def _trace_id(request: Request) -> str:
    """从日志中间件读取 trace_id，保证响应体和响应头能对上同一次请求。"""

    return getattr(request.state, "trace_id", "unknown")


def _trace_path(request: Request) -> Path | None:
    """读取测试或运行时指定的 trace 路径。

    默认返回 None，让 recorder 使用 `eval/traces/traces.jsonl`；测试可以通过 `app.state`
    指到临时文件，避免污染真实评测 trace。
    """

    path = getattr(request.app.state, "trace_path", None)
    return Path(path) if path is not None else None


def _build_answer(answer_hint: str, rows: list[dict[str, Any]]) -> str:
    """用最小模板把表格结果转成自然语言答案。

    M5 仍不追求复杂报告，只把“首行重点 + 总行数”讲清楚，保证演示页不用直接让用户读
    原始表格。
    """

    if not rows:
        return f"{answer_hint}：暂无数据。"

    first_row = rows[0]
    summary = "，".join(f"{key}={value}" for key, value in first_row.items())
    return f"{answer_hint}：{summary}（共 {len(rows)} 行结果）"


def _elapsed_ms(started_at: float) -> float:
    """返回保留 3 位小数的毫秒耗时。"""

    return round((perf_counter() - started_at) * 1000, 3)


def _record_trace(
    *,
    request: Request,
    request_body: QueryRequest,
    response: AgentResponse,
    trace_steps: list[TraceStep] | None = None,
    langfuse_trace_id: str | None = None,
    langfuse_trace_url: str | None = None,
    langfuse_write_status: str = "skipped",
    langfuse_span_mode: str = "post_hoc",
) -> None:
    """把 AgentResponse 的关键信息同步追加到 JSONL trace。"""

    trace_record = TraceRecord(
        trace_id=response.trace_id,
        question=request_body.question,
        user_role=request_body.user_role,
        route=response.route,
        answer=response.answer,
        sql=response.sql,
        columns=response.columns,
        rows=response.rows,
        tables_used=response.tables_used,
        docs_used=response.docs_used,
        chart_spec=response.chart_spec,
        safety_status=response.safety_status,
        blocked_reason=response.blocked_reason,
        cost=response.cost,
        tool_calls=response.tool_calls,
        trace_steps=trace_steps or [],
        error_type=response.error_type,
        langfuse_trace_id=langfuse_trace_id,
        langfuse_trace_url=langfuse_trace_url,
        langfuse_write_status=langfuse_write_status,
        langfuse_span_mode=langfuse_span_mode,
    )
    path = _trace_path(request)
    if path is None:
        append_trace(trace_record)
    else:
        append_trace(trace_record, path=path)


def _blocked_response(
    *,
    request: Request,
    request_body: QueryRequest,
    trace_id: str,
    sql: str | None,
    blocked_reason: str,
    started_at: float,
    tool_call: ToolCallTrace | None = None,
    error_type: str = "sql_guard_blocked",
    trace_steps: list[TraceStep] | None = None,
    langfuse_trace_id: str | None = None,
    langfuse_trace_url: str | None = None,
    langfuse_write_status: str = "skipped",
    langfuse_span_mode: str = "post_hoc",
) -> AgentResponse:
    """构造统一的拦截响应，并同步写 trace。"""

    tool_calls = [
        tool_call
        or ToolCallTrace(
            tool_name="sql_guard",
            status="blocked",
            latency_ms=0.0,
            sql=sql,
            error_type=error_type,
            message=blocked_reason,
        )
    ]

    response = AgentResponse(
        route="sql",
        answer="SQL Guard 已拦截该请求。",
        sql=sql,
        columns=[],
        rows=[],
        tables_used=[],
        docs_used=[],
        chart_spec=None,
        safety_status="blocked",
        blocked_reason=blocked_reason,
        cost=CostInfo(latency_ms=_elapsed_ms(started_at), sql_time_ms=0.0),
        tool_calls=tool_calls,
        error_type=error_type,
        trace_id=trace_id,
    )
    _record_trace(
        request=request,
        request_body=request_body,
        response=response,
        trace_steps=trace_steps,
        langfuse_trace_id=langfuse_trace_id,
        langfuse_trace_url=langfuse_trace_url,
        langfuse_write_status=langfuse_write_status,
        langfuse_span_mode=langfuse_span_mode,
    )
    return response


def _resolve_sql(request_body: QueryRequest) -> tuple[str, dict[str, str], str]:
    """解析自然语言请求对应的 SQL。

    返回值按 `(sql, parameters, answer_hint)` 组织。模板命中时沿用 M3 参数化 SQL；模板未
    命中时走 M4 LLM 生成路径，生成 SQL 目前不带绑定参数。
    """

    matched = match_template(request_body.question)
    if matched is not None:
        return matched.sql, matched.parameters, matched.answer_hint

    domain_schema = load_domain_schema()
    generated = generate_sql(
        question=request_body.question,
        user_role=request_body.user_role,
        domain_schema=domain_schema,
    )
    return generated.sql, {}, "LLM SQL 查询结果"


def _success_response(
    *,
    request: Request,
    request_body: QueryRequest,
    trace_id: str,
    sql: str,
    answer_hint: str,
    tool_result: SQLToolResult,
    started_at: float,
    trace_steps: list[TraceStep] | None = None,
    chart_spec: dict[str, Any] | None = None,
    langfuse_trace_id: str | None = None,
    langfuse_trace_url: str | None = None,
    langfuse_write_status: str = "skipped",
    langfuse_span_mode: str = "post_hoc",
) -> AgentResponse:
    """把 SQL Tool 结果整理成 M5 AgentResponse，并追加 trace。"""

    resolved_chart_spec = chart_spec
    if resolved_chart_spec is None:
        resolved_chart_spec = build_chart_spec(columns=tool_result.columns, rows=tool_result.rows, question=request_body.question)
    response = AgentResponse(
        route="sql",
        answer=_build_answer(answer_hint, tool_result.rows),
        sql=sql,
        columns=tool_result.columns,
        rows=tool_result.rows,
        tables_used=tool_result.tables_used,
        docs_used=[],
        chart_spec=resolved_chart_spec,
        safety_status="passed",
        blocked_reason=None,
        cost=CostInfo(
            latency_ms=_elapsed_ms(started_at),
            sql_time_ms=tool_result.sql_time_ms,
            model=None,
            prompt_tokens=0,
            completion_tokens=0,
        ),
        tool_calls=[tool_result.tool_call] if tool_result.tool_call else [],
        error_type=None,
        trace_id=trace_id,
    )
    _record_trace(
        request=request,
        request_body=request_body,
        response=response,
        trace_steps=trace_steps,
        langfuse_trace_id=langfuse_trace_id,
        langfuse_trace_url=langfuse_trace_url,
        langfuse_write_status=langfuse_write_status,
        langfuse_span_mode=langfuse_span_mode,
    )
    return response


@router.post("/query", response_model=AgentResponse)
def query(request_body: QueryRequest, request: Request, db: Session = Depends(get_db)) -> AgentResponse:
    """执行 M5 查询闭环。

    处理顺序：
    1. 先匹配模板；
    2. 模板未命中时，如果用户输入本身像危险 SQL，旧链路先用 M3 只读 Guard 直接拦截；
    3. 其他未命中问题调用 LLM 生成 SQL；
    4. SQL 统一交给 M5 SQL Tool，返回表格、工具调用和耗时；
    5. 聚合结果尝试生成 chart_spec，并把完整过程写入 JSONL trace。
    """

    started_at = perf_counter()
    trace_id = _trace_id(request)
    matched = match_template(request_body.question)

    # 步骤 0：M11 评测开关显式绕过模板优先，只走新 Text2SQL pipeline。-----------------------
    if request_body.force_new_pipeline:
        pipeline_result = run_text2sql_pipeline(
            question=request_body.question,
            user_role=request_body.user_role,
            db=db,
            trace_id=trace_id,
            schema_retrieval_profile=request_body.schema_retrieval_profile,
        )
        if pipeline_result.tool_result is None or pipeline_result.safety_status != "passed":
            return _blocked_response(
                request=request,
                request_body=request_body,
                trace_id=trace_id,
                sql=pipeline_result.sql,
                blocked_reason=pipeline_result.blocked_reason or "新 Text2SQL pipeline 已拦截该请求。",
                started_at=started_at,
                tool_call=pipeline_result.tool_call,
                error_type=pipeline_result.error_type or "text2sql_pipeline_blocked",
                trace_steps=pipeline_result.trace_steps,
                langfuse_trace_id=pipeline_result.langfuse_trace_id,
                langfuse_trace_url=pipeline_result.langfuse_trace_url,
                langfuse_write_status=pipeline_result.langfuse_write_status,
                langfuse_span_mode=pipeline_result.langfuse_span_mode,
            )
        return _success_response(
            request=request,
            request_body=request_body,
            trace_id=trace_id,
            sql=pipeline_result.sql or "",
            answer_hint=pipeline_result.answer_hint,
            tool_result=pipeline_result.tool_result,
            started_at=started_at,
            trace_steps=pipeline_result.trace_steps,
            chart_spec=pipeline_result.chart_spec,
            langfuse_trace_id=pipeline_result.langfuse_trace_id,
            langfuse_trace_url=pipeline_result.langfuse_trace_url,
            langfuse_write_status=pipeline_result.langfuse_write_status,
            langfuse_span_mode=pipeline_result.langfuse_span_mode,
        )

    if matched is None and looks_like_dangerous_sql(request_body.question):
        guard_result = validate_readonly_sql(request_body.question)
        if not guard_result.is_allowed:
            return _blocked_response(
                request=request,
                request_body=request_body,
                trace_id=trace_id,
                sql=request_body.question,
                blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
                started_at=started_at,
            )

    try:
        sql, parameters, answer_hint = _resolve_sql(request_body)
    except LLMGenerationError as exc:
        return _blocked_response(
            request=request,
            request_body=request_body,
            trace_id=trace_id,
            sql=None,
            blocked_reason=f"LLM SQL 生成失败：{exc}",
            started_at=started_at,
            tool_call=ToolCallTrace(
                tool_name="llm_sql_generator",
                status="error",
                latency_ms=_elapsed_ms(started_at),
                error_type="llm_generation_error",
                message=str(exc),
            ),
            error_type="llm_generation_error",
        )

    domain_schema = load_domain_schema()
    tool_result = run_sql_tool(
        db=db,
        sql=sql,
        parameters=parameters,
        user_role=request_body.user_role,
        trace_id=trace_id,
        domain_schema=domain_schema,
    )
    if tool_result.safety_status != "passed":
        return _blocked_response(
            request=request,
            request_body=request_body,
            trace_id=trace_id,
            sql=sql,
            blocked_reason=tool_result.blocked_reason or "SQL Guard 已拦截。",
            started_at=started_at,
            tool_call=tool_result.tool_call,
            error_type=tool_result.error_type or "sql_guard_blocked",
        )

    return _success_response(
        request=request,
        request_body=request_body,
        trace_id=trace_id,
        sql=sql,
        answer_hint=answer_hint,
        tool_result=tool_result,
        started_at=started_at,
    )
