"""M3 `/api/query`：自然语言问题 → 模板 SQL → SQL Guard → 数据库执行 → AgentResponse。

★ 这是 DataPilot v0 的核心闭环。它不调用 LLM，只执行白名单模板 SQL，并且所有 SQL
必须先过 SQL Guard，避免为了演示方便绕开安全入口。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentResponse, QueryRequest
from engine.nl2sql.templates import match_template
from engine.sql_guard.guard import validate_readonly_sql


router = APIRouter(prefix="/api", tags=["query"])


def _trace_id(request: Request) -> str:
    """从日志中间件读取 trace_id，保证响应体和响应头能对上同一次请求。"""

    return getattr(request.state, "trace_id", "unknown")


def _jsonable(value: Any) -> Any:
    """把数据库返回值转换成 JSON 可序列化值。

    Decimal 和 datetime 是数据库查询里最常见的非 JSON 原生类型，FastAPI 虽能辅助处理，
    这里先显式转换，便于 EvalOps 后续直接写 JSONL。
    """

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _row_to_dict(row: RowMapping) -> dict[str, Any]:
    """把 SQLAlchemy RowMapping 转成普通 dict。"""

    return {key: _jsonable(value) for key, value in row.items()}


def _build_answer(answer_hint: str, rows: list[dict[str, Any]]) -> str:
    """用最小模板把表格首行转成自然语言答案。

    M3 不追求复杂报告，只给用户一个能读懂的摘要；M5 会再扩展更完整的 answer 生成。
    """

    if not rows:
        return f"{answer_hint}：暂无数据。"

    first_row = rows[0]
    summary = "，".join(f"{key}={value}" for key, value in first_row.items())
    return f"{answer_hint}：{summary}"


def _blocked_response(*, trace_id: str, sql: str | None, blocked_reason: str) -> AgentResponse:
    """构造统一的 SQL Guard 拦截响应。"""

    return AgentResponse(
        route="sql",
        answer="SQL Guard 已拦截该请求。",
        sql=sql,
        columns=[],
        rows=[],
        safety_status="blocked",
        blocked_reason=blocked_reason,
        trace_id=trace_id,
    )


@router.post("/query", response_model=AgentResponse)
def query(request_body: QueryRequest, request: Request, db: Session = Depends(get_db)) -> AgentResponse:
    """执行 M3 v0 查询闭环。

    处理顺序：
    1. 先匹配模板；
    2. 没命中模板时，如果用户输入本身像 SQL，则也交给 Guard 给出结构化拦截；
    3. 命中模板后先 Guard，再执行数据库查询。
    """

    trace_id = _trace_id(request)
    matched = match_template(request_body.question)

    if matched is None:
        guard_result = validate_readonly_sql(request_body.question)
        if not guard_result.is_allowed:
            return _blocked_response(
                trace_id=trace_id,
                sql=request_body.question,
                blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
            )
        return _blocked_response(
            trace_id=trace_id,
            sql=None,
            blocked_reason="未命中 v0 模板 SQL，M3 不调用 LLM 自由生成。",
        )

    guard_result = validate_readonly_sql(matched.sql)
    if not guard_result.is_allowed:
        return _blocked_response(
            trace_id=trace_id,
            sql=matched.sql,
            blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
        )

    try:
        result = db.execute(text(matched.sql), matched.parameters)
    except SQLAlchemyError as exc:
        return _blocked_response(
            trace_id=trace_id,
            sql=matched.sql,
            blocked_reason=f"SQL 执行失败：{exc}",
        )

    columns = list(result.keys())
    rows = [_row_to_dict(row) for row in result.mappings().all()]
    return AgentResponse(
        route=matched.route,  # type: ignore[arg-type]
        answer=_build_answer(matched.answer_hint, rows),
        sql=matched.sql,
        columns=columns,
        rows=rows,
        safety_status="passed",
        blocked_reason=None,
        trace_id=trace_id,
    )

