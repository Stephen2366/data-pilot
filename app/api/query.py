"""M4 `/api/query`：自然语言问题 → 模板 / LLM SQL → SQL Guard + RBAC → 数据库执行。

★ M4 仍然模板优先：M3 已验证过的高价值问题继续走稳定模板；模板未命中时才调用 LLM
生成 SQL。无论 SQL 来自哪里，都必须先过增强版 SQL Guard。
"""

from __future__ import annotations

import re
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
from engine.nl2sql.generator import LLMGenerationError, generate_sql
from engine.nl2sql.schema_loader import load_domain_schema
from engine.nl2sql.templates import match_template
from engine.sql_guard.guard import validate_readonly_sql
from engine.sql_guard.policy import validate_sql_policy


router = APIRouter(prefix="/api", tags=["query"])

DANGEROUS_SQL_KEYWORDS = ("drop", "delete", "update", "insert", "alter", "truncate")


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


def _looks_like_dangerous_sql(text: str) -> bool:
    """判断用户输入是否明显在要求执行危险 SQL。

    M3 没有 LLM，未命中模板可以直接交给 Guard；M4 需要让普通自然语言进入 LLM。
    因此这里只提前拦截 DDL / DML 关键词，prompt injection 里的危险 SQL 也会被抓住。
    """

    normalized = text.lower()
    return any(re.search(rf"\b{keyword}\b", normalized) for keyword in DANGEROUS_SQL_KEYWORDS)


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


@router.post("/query", response_model=AgentResponse)
def query(request_body: QueryRequest, request: Request, db: Session = Depends(get_db)) -> AgentResponse:
    """执行 M4 查询闭环。

    处理顺序：
    1. 先匹配模板；
    2. 模板未命中时，如果用户输入本身像危险 SQL，先用 M3 只读 Guard 直接拦截；
    3. 其他未命中问题调用 LLM 生成 SQL；
    4. 所有 SQL 统一经过 M4 policy，再执行数据库查询。
    """

    trace_id = _trace_id(request)
    matched = match_template(request_body.question)

    if matched is None and _looks_like_dangerous_sql(request_body.question):
        guard_result = validate_readonly_sql(request_body.question)
        if not guard_result.is_allowed:
            return _blocked_response(
                trace_id=trace_id,
                sql=request_body.question,
                blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
            )

    try:
        sql, parameters, answer_hint = _resolve_sql(request_body)
    except LLMGenerationError as exc:
        return _blocked_response(
            trace_id=trace_id,
            sql=None,
            blocked_reason=f"LLM SQL 生成失败：{exc}",
        )

    domain_schema = load_domain_schema()
    guard_result = validate_sql_policy(sql, user_role=request_body.user_role, domain_schema=domain_schema)
    if not guard_result.is_allowed:
        return _blocked_response(
            trace_id=trace_id,
            sql=sql,
            blocked_reason=guard_result.blocked_reason or "SQL Guard 已拦截。",
        )

    try:
        result = db.execute(text(sql), parameters)
    except SQLAlchemyError as exc:
        return _blocked_response(
            trace_id=trace_id,
            sql=sql,
            blocked_reason=f"SQL 执行失败：{exc}",
        )

    columns = list(result.keys())
    rows = [_row_to_dict(row) for row in result.mappings().all()]
    return AgentResponse(
        route="sql",
        answer=_build_answer(answer_hint, rows),
        sql=sql,
        columns=columns,
        rows=rows,
        safety_status="passed",
        blocked_reason=None,
        trace_id=trace_id,
    )
