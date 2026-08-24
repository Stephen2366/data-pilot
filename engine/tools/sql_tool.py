"""M5 SQL Tool：统一封装 SQL Guard、数据库执行、耗时和工具调用记录。

★ M4 的 `/api/query` 直接 `db.execute()`，能跑但不利于 EvalOps 复盘。M5 把 SQL 查询变成
一个明确的 tool：输入 SQL / role / trace_id，输出表格、耗时、安全状态和 tool trace。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.schemas.agent import ToolCallTrace
from engine.nl2sql.schema_loader import DomainSchema
from engine.sql_guard.policy import extract_sql_access, validate_sql_policy
from engine.trace.lifecycle import TraceContext


logger = logging.getLogger(__name__)
_SAFE_SQL_EXECUTION_MESSAGE = "SQL 执行失败。"
_MYSQL_FUNCTION_NOT_FOUND = 1305
_MYSQL_UNSUPPORTED_DATE_TRUNC = "mysql_unsupported_date_trunc"


@dataclass(frozen=True)
class SQLToolResult:
    """SQL Tool 的结构化返回值。

    `safety_status=blocked` 或 `error_type is not None` 时，调用方只能返回结构化错误，不继续
    生成图表或假装查询成功。
    """

    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    tables_used: list[str] = field(default_factory=list)
    safety_status: str = "passed"
    blocked_reason: str | None = None
    sql_time_ms: float = 0.0
    tool_call: ToolCallTrace | None = None
    error_type: str | None = None
    # `issue_code` 是给上层 Controller 的 closed-world 技术分类，不承载 driver 原文。
    issue_code: str | None = None


def _jsonable(value: Any) -> Any:
    """把数据库返回值转换成 JSON / JSONL 都能直接写出的值。"""

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row_to_dict(row: RowMapping) -> dict[str, Any]:
    """把 SQLAlchemy RowMapping 转成普通 dict，避免响应层依赖 SQLAlchemy 类型。"""

    return {key: _jsonable(value) for key, value in row.items()}


def _classify_execution_issue(sql: str, exc: SQLAlchemyError) -> str | None:
    """把真实 DBAPI 异常收敛成极窄的安全 code，禁止上层解析 raw error 文本。

    ★ MySQL 1305 表示调用的函数不存在；只有候选 SQL 自身确实包含 `DATE_TRUNC` 时，
    才能归类为 M44 已准入的一次修复场景。连接中断、权限错误或其他函数错误即使也执行
    失败，都会保持 generic `sql_execution_error`，避免扩大自动重试边界。
    """

    if "date_trunc" not in sql.lower():
        return None
    original = getattr(exc, "orig", None)
    arguments = getattr(original, "args", ())
    if not arguments:
        return None
    try:
        error_number = int(arguments[0])
    except (TypeError, ValueError):
        return None
    return _MYSQL_UNSUPPORTED_DATE_TRUNC if error_number == _MYSQL_FUNCTION_NOT_FOUND else None


def run_sql_tool(
    *,
    db: Session,
    sql: str,
    parameters: dict[str, Any],
    user_role: str,
    trace_id: str,
    domain_schema: DomainSchema,
    trace_context: TraceContext | None = None,
    trace_parent_step_id: str | None = None,
) -> SQLToolResult:
    """★ 执行一次受 SQL Guard 保护的查询。

    处理顺序固定为：先 policy 校验，再提取表名，再执行数据库。这样即便未来换成 Agent
    编排，SQL Tool 的安全边界也不会被绕开。

    `trace_context` 是 M16B 的可选 lifecycle 接口：新 Text2SQL pipeline 传入后，SQL Tool
    会在真实边界内记录 `sql_guard` / `sql_execution` spans；旧模板链路不传，行为保持不变。
    """

    started_at = perf_counter()

    # 步骤 1：所有 SQL 来源统一先过 M4 policy ------------------------------------------------
    guard_span = trace_context.start_span(
        name="sql_guard",
        step_type="sql_guard",
        input_summary="validate generated SQL",
        parent_step_id=trace_parent_step_id,
    ) if trace_context is not None else None
    guard_result = validate_sql_policy(sql, user_role=user_role, domain_schema=domain_schema)
    if not guard_result.is_allowed:
        latency_ms = _elapsed_ms(started_at)
        if guard_span is not None:
            guard_span.end(
                status="blocked",
                output_summary=guard_result.blocked_reason or "SQL Guard blocked",
                error_type="sql_guard_blocked",
                metadata={"blocked_reason": guard_result.blocked_reason},
            )
        tool_call = ToolCallTrace(
            tool_name="sql_guard",
            status="blocked",
            latency_ms=latency_ms,
            sql=sql,
            error_type="sql_guard_blocked",
            message=guard_result.blocked_reason,
        )
        return SQLToolResult(
            safety_status="blocked",
            blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
            sql_time_ms=0.0,
            tool_call=tool_call,
            error_type="sql_guard_blocked",
        )

    # 步骤 2：安全通过后提取 tables_used，供响应体和 trace 共用。----------------------------
    access = extract_sql_access(sql, domain_schema)
    tables_used = sorted(access.tables)
    if guard_span is not None:
        guard_span.end(
            output_summary="SQL Guard passed",
            metadata={"tables_used": tables_used, "blocked_reason": None},
        )

    # 步骤 3：执行数据库查询并记录 SQL tool 耗时。-------------------------------------------
    execution_span = trace_context.start_span(
        name="sql_execution",
        step_type="sql_query",
        input_summary="execute generated SQL",
        metadata={"tables_used": tables_used},
        parent_step_id=trace_parent_step_id,
    ) if trace_context is not None else None
    try:
        result = db.execute(text(sql), parameters)
    except SQLAlchemyError as exc:
        latency_ms = _elapsed_ms(started_at)
        issue_code = _classify_execution_issue(sql, exc)
        # 详细异常只进入受控本地日志；Response、Observation、Trace 一律使用下面的安全话术。
        logger.exception(
            "SQL 执行失败，公开投影已脱敏",
            extra={"trace_id": trace_id, "tables_used": tables_used, "issue_code": issue_code},
        )
        if execution_span is not None:
            execution_span.fail(
                output_summary=_SAFE_SQL_EXECUTION_MESSAGE,
                error_type="sql_execution_error",
                metadata={
                    "tables_used": tables_used,
                    "latency_ms": latency_ms,
                    "issue_code": issue_code,
                },
            )
        tool_call = ToolCallTrace(
            tool_name="sql_query",
            status="error",
            latency_ms=latency_ms,
            sql=sql,
            tables_used=tables_used,
            error_type="sql_execution_error",
            message=_SAFE_SQL_EXECUTION_MESSAGE,
        )
        return SQLToolResult(
            tables_used=tables_used,
            safety_status="blocked",
            blocked_reason=_SAFE_SQL_EXECUTION_MESSAGE,
            sql_time_ms=latency_ms,
            tool_call=tool_call,
            error_type="sql_execution_error",
            issue_code=issue_code,
        )

    columns = list(result.keys())
    rows = [_row_to_dict(row) for row in result.mappings().all()]
    latency_ms = _elapsed_ms(started_at)
    if execution_span is not None:
        execution_span.end(
            output_summary=_sql_execution_summary(rows),
            metadata={
                "row_count": len(rows),
                "column_count": len(columns),
                "latency_ms": latency_ms,
                "tables_used": tables_used,
            },
        )
    tool_call = ToolCallTrace(
        tool_name="sql_query",
        status="success",
        latency_ms=latency_ms,
        sql=sql,
        tables_used=tables_used,
    )
    return SQLToolResult(
        columns=columns,
        rows=rows,
        tables_used=tables_used,
        safety_status="passed",
        sql_time_ms=latency_ms,
        tool_call=tool_call,
    )


def _elapsed_ms(started_at: float) -> float:
    """返回保留 3 位小数的毫秒耗时，便于测试和日志稳定阅读。"""

    return round((perf_counter() - started_at) * 1000, 3)


def _sql_execution_summary(rows: list[dict[str, Any]]) -> str:
    """把 SQL 执行结果压成一句话，供 lifecycle span 和 pipeline trace 共用口径。"""

    if not rows:
        return "暂无数据。"
    first_row = rows[0]
    first_row_summary = "，".join(f"{key}={value}" for key, value in first_row.items())
    return f"首行：{first_row_summary}（共 {len(rows)} 行结果）"
