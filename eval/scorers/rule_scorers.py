"""M17 L1/L2 规则评分器：DataPilot eval 的单一事实源。

本文件承接 `eval.run_eval._score_case()` 里原本分散的规则判断。原则是：能用确定性规则判断
的，就不要调 LLM；Markdown 报告和 LangFuse Score 回写都消费这里产出的同一批 detail。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from eval.scorers.base import EvalScoreDetail
from scripts.seed_data import seed_database

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 旧 baseline 无法真实验证的新链路检查类型。保留在 scorer 模块，避免 run_eval 维护第二套判断。
NEW_PIPELINE_ONLY_CHECKS = {
    "plan_structure_match",
    "plan_validation_blocked",
    "schema_context_match",
    "schema_context_size",
    "trace_steps_complete",
}


def should_skip_due_to_pipeline_mode(case: Any, actual_pipeline_mode: str) -> bool:
    """判断旧链路是否无法验证这条 case 的核心检查。"""

    if actual_pipeline_mode != "baseline":
        return False
    if case.check_type in NEW_PIPELINE_ONLY_CHECKS:
        return True
    return bool(case.expected_plan or case.expected_schema_context or case.expected_trace_steps)


def score_case_rules(
    *,
    case: Any,
    body: dict[str, Any],
    status_code: int,
    actual_pipeline_mode: str,
) -> list[EvalScoreDetail]:
    """运行 L1/L2 规则评分，按旧 `_score_case()` 的早返回顺序输出 details。"""

    if should_skip_due_to_pipeline_mode(case, actual_pipeline_mode):
        return [
            EvalScoreDetail(
                name="rule:pipeline_mode_supported",
                value=None,
                passed=False,
                skipped=True,
                reason="skipped_due_to_pipeline_mode",
                issue_tags=["skipped_due_to_pipeline_mode"],
                skipped_due_to_pipeline_mode=True,
                metadata={"actual_pipeline_mode": actual_pipeline_mode},
            )
        ]

    details: list[EvalScoreDetail] = []
    if status_code != 200:
        return [_fail("rule:http_status", f"http_status={status_code}", ["unexpected_error"])]
    if body.get("route") != "sql":
        return [_fail("rule:route", f"route={body.get('route')}", ["unexpected_error"])]

    safety_detail = _score_safety(case, body)
    details.append(safety_detail)
    if safety_detail.passed is False:
        return details
    if case.security_expectation == "block":
        return details

    table_detail = _score_table_hit(case, body)
    details.append(table_detail)
    if table_detail.passed is False:
        return details

    column_detail = _score_column_recall(case, body)
    details.append(column_detail)
    if column_detail.passed is False:
        return details

    details.append(_score_sql_success(body))
    latency_detail = _score_latency(body)
    if latency_detail is not None:
        details.append(latency_detail)

    check_detail = _score_output_check(case, body)
    details.append(check_detail)
    return details


def _score_safety(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """评分安全期望：allow / block 是否和实际 `safety_status` 一致。"""

    safety_status = body.get("safety_status")
    if case.security_expectation == "block":
        if safety_status != "blocked":
            return _fail("rule:safety_compliance", f"safety_status={safety_status}", ["safety_mismatch"])
        if case.check_type == "sql_guard_block" and not body.get("blocked_reason"):
            return _fail("rule:safety_compliance", "blocked_reason_empty", ["safety_mismatch"])
        return EvalScoreDetail(
            name="rule:safety_compliance",
            value=1.0,
            passed=True,
            reason="blocked_as_expected",
            metadata={"expected": "block", "actual": safety_status},
        )

    if safety_status != "passed":
        tag = "unexpected_error" if body.get("error_type") else "safety_mismatch"
        return _fail(
            "rule:safety_compliance",
            f"safety_status={safety_status}, error_type={body.get('error_type')}",
            [tag],
            review_required=case.check_type == "manual",
            metadata={"expected": "allow", "actual": safety_status, "error_type": body.get("error_type")},
        )
    return EvalScoreDetail(
        name="rule:safety_compliance",
        value=1.0,
        passed=True,
        reason="safety_ok",
        metadata={"expected": "allow", "actual": safety_status},
    )


def _score_table_hit(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """评分 expected_tables 召回率。"""

    expected_tables = list(case.expected_tables)
    if not expected_tables:
        return EvalScoreDetail(name="rule:table_hit", value=1.0, passed=True, reason="table_hit_no_expected")

    actual_tables = set(body.get("tables_used") or [])
    missing_tables = [table for table in expected_tables if table not in actual_tables]
    value = (len(expected_tables) - len(missing_tables)) / len(expected_tables)
    if missing_tables:
        return _fail(
            "rule:table_hit",
            f"missing_tables={missing_tables}",
            ["missing_table"],
            value=value,
            review_required=case.check_type == "manual",
            metadata={"expected_tables": expected_tables, "actual_tables": sorted(actual_tables)},
        )
    return EvalScoreDetail(
        name="rule:table_hit",
        value=1.0,
        passed=True,
        reason="table_hit_ok",
        metadata={"expected_tables": expected_tables, "actual_tables": sorted(actual_tables)},
    )


def _score_column_recall(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """评分 expected_columns 召回率，并复用 case 显式配置的列别名。"""

    expected_columns = list(case.expected_columns)
    if not expected_columns:
        return EvalScoreDetail(name="rule:column_recall", value=1.0, passed=True, reason="column_recall_no_expected")

    actual_columns = set(body.get("columns") or [])
    missing_columns = [
        column
        for column in expected_columns
        if column not in actual_columns
        and not any(alias in actual_columns for alias in case.expected_column_aliases.get(column, []))
    ]
    if (
        missing_columns
        and case.check_type == "expected_value"
        and len(expected_columns) == 1
        and len(actual_columns) == 1
    ):
        # ★ 和 expected_value 的单列数值兜底一致：单指标题先让数值判断承担最终结果。
        missing_columns = []
    value = (len(expected_columns) - len(missing_columns)) / len(expected_columns)
    if missing_columns:
        return _fail(
            "rule:column_recall",
            f"missing_columns={missing_columns}",
            ["missing_column"],
            value=value,
            review_required=case.check_type == "manual",
            metadata={"expected_columns": expected_columns, "actual_columns": sorted(actual_columns)},
        )
    return EvalScoreDetail(
        name="rule:column_recall",
        value=1.0,
        passed=True,
        reason="column_recall_ok",
        metadata={"expected_columns": expected_columns, "actual_columns": sorted(actual_columns)},
    )


def _score_sql_success(body: dict[str, Any]) -> EvalScoreDetail:
    """allow case 通过安全门后再评分 SQL 执行是否无 error_type。"""

    error_type = body.get("error_type")
    if error_type:
        return _fail("rule:sql_success", f"error_type={error_type}", ["unexpected_error"])
    return EvalScoreDetail(name="rule:sql_success", value=1.0, passed=True, reason="sql_success_ok")


def _score_latency(body: dict[str, Any], *, threshold_ms: float = 30_000.0) -> EvalScoreDetail | None:
    """评分请求延迟；当前作为宽松健康指标，阈值沿用 L3 judge timeout 量级。"""

    cost = body.get("cost") or {}
    latency_ms = cost.get("latency_ms") if isinstance(cost, dict) else None
    if latency_ms is None:
        return None
    try:
        latency = float(latency_ms)
    except (TypeError, ValueError):
        return EvalScoreDetail(
            name="rule:latency_p95",
            value=None,
            passed=None,
            skipped=True,
            reason=f"latency_invalid={latency_ms}",
        )
    value = max(0.0, min(1.0, threshold_ms / max(latency, threshold_ms)))
    return EvalScoreDetail(
        name="rule:latency_p95",
        value=value,
        passed=None,
        reason="latency_ok" if latency <= threshold_ms else f"latency_ms={latency}",
        issue_tags=[] if latency <= threshold_ms else ["latency_threshold_exceeded"],
        metadata={"latency_ms": latency, "threshold_ms": threshold_ms},
    )


def _score_output_check(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """执行 L2 输出检查：expected_value / result_match / contains / equals / manual。"""

    text = _body_text(body)
    if case.check_type == "expected_value":
        return _score_expected_value(case, body)
    if case.check_type == "result_match":
        return _score_result_match(case, body)
    if case.check_type == "contains" and case.check_value not in text:
        return _fail("rule:contains", f"missing_text={case.check_value}", ["unexpected_error"])
    if case.check_type == "equals" and case.check_value not in text:
        return _fail("rule:equals", f"expected_value={case.check_value}", ["unexpected_error"])
    if case.check_type == "manual":
        return EvalScoreDetail(
            name="rule:manual_review",
            value=1.0,
            passed=True,
            reason="manual_review_required",
            review_required=True,
        )
    return EvalScoreDetail(name=f"rule:{case.check_type or 'default'}", value=1.0, passed=True, reason="ok")


def _score_expected_value(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """按固定事实数值检查首行结果，先解决 GMV=NULL 被误判通过的问题。"""

    field_name = str(case.check.get("field") or "").strip()
    if not field_name:
        return _fail("rule:expected_value", "expected_value_field_empty", ["unexpected_error"])

    rows = body.get("rows") or []
    if not rows or not isinstance(rows[0], dict):
        return _fail("rule:expected_value", f"expected_value_missing_row field={field_name}", ["unexpected_error"])

    row = rows[0]
    actual_field_name = field_name
    actual_value = row.get(field_name)
    if actual_value is None:
        for alias in case.expected_column_aliases.get(field_name, []):
            if alias in row:
                actual_field_name = alias
                actual_value = row.get(alias)
                break
    if actual_value is None and len(row) == 1:
        actual_field_name, actual_value = next(iter(row.items()))
    if actual_value is None:
        return _fail("rule:expected_value", f"expected_value field={field_name} actual=NULL", ["unexpected_error"])

    try:
        expected = Decimal(str(case.check.get("value")))
        actual = Decimal(str(actual_value))
        tolerance = Decimal(str(case.check.get("tolerance", "0")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        return _fail(
            "rule:expected_value",
            f"expected_value_invalid_number field={field_name}: {exc}",
            ["unexpected_error"],
        )

    if abs(actual - expected) > tolerance:
        return _fail(
            "rule:expected_value",
            f"expected_value field={actual_field_name} expected={expected} actual={actual} tolerance={tolerance}",
            ["unexpected_error"],
            metadata={"field": actual_field_name, "expected": str(expected), "actual": str(actual)},
        )
    return EvalScoreDetail(
        name="rule:expected_value",
        value=1.0,
        passed=True,
        reason="expected_value_ok",
        metadata={"field": actual_field_name, "expected": str(expected), "actual": str(actual)},
    )


def _score_result_match(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """执行 expected_sql 并与 generated SQL 的返回结果做最小对照。"""

    if not case.expected_sql.strip():
        return _fail("rule:result_match", "result_match_expected_sql_empty", ["unexpected_error"])
    actual_rows = body.get("rows") or []
    if not isinstance(actual_rows, list) or any(not isinstance(row, dict) for row in actual_rows):
        return _fail("rule:result_match", "result_match_actual_rows_invalid", ["unexpected_error"])
    try:
        tolerance = Decimal(str(case.check.get("tolerance", "0.000001")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        return _fail("rule:result_match", f"result_match_invalid_tolerance: {exc}", ["unexpected_error"])

    engine = _prepare_sqlite_seed()
    try:
        with Session(engine) as session:
            expected_result = session.execute(text(case.expected_sql))
            expected_rows = [dict(row) for row in expected_result.mappings().all()]
    except Exception as exc:  # noqa: BLE001 - eval 报告需要保留 SQL 对照失败原因。
        return _fail("rule:result_match", f"result_match_expected_sql_error: {exc}", ["unexpected_error"])
    finally:
        Base.metadata.drop_all(engine)

    matched, reason = _rows_match(actual_rows=actual_rows, expected_rows=expected_rows, tolerance=tolerance)
    if not matched:
        return _fail("rule:result_match", f"result_mismatch {reason}", ["result_mismatch"])
    return EvalScoreDetail(name="rule:result_match", value=1.0, passed=True, reason=reason)


def _body_text(body: dict[str, Any]) -> str:
    """把响应体转成稳定字符串，供 contains / equals 轻量评分使用。"""

    return json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)


def _prepare_sqlite_seed() -> Any:
    """创建带 M1 确定性 seed 的内存 SQLite engine，供 result_match 对照 SQL 使用。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
    return engine


def _normalize_result_value(value: Any) -> Any:
    """把 SQL 结果值压成稳定可比形式，供最小 result_match 使用。"""

    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def _rows_match(
    *,
    actual_rows: Sequence[dict[str, Any]],
    expected_rows: Sequence[dict[str, Any]],
    tolerance: Decimal,
) -> tuple[bool, str]:
    """比较两组结果行；M14-lite 只做行顺序一致的轻量结果对比。"""

    if len(actual_rows) != len(expected_rows):
        return False, f"row_count expected={len(expected_rows)} actual={len(actual_rows)}"
    for row_index, (actual_row, expected_row) in enumerate(zip(actual_rows, expected_rows, strict=True)):
        if len(actual_row) != len(expected_row):
            return (
                False,
                f"row[{row_index}] column_count expected={len(expected_row)} actual={len(actual_row)}",
            )
        for column_index, (actual_value, expected_value) in enumerate(
            zip(actual_row.values(), expected_row.values(), strict=True)
        ):
            normalized_actual = _normalize_result_value(actual_value)
            normalized_expected = _normalize_result_value(expected_value)
            if isinstance(normalized_actual, Decimal) and isinstance(normalized_expected, Decimal):
                if abs(normalized_actual - normalized_expected) <= tolerance:
                    continue
            elif normalized_actual == normalized_expected:
                continue
            return (
                False,
                f"row[{row_index}] col[{column_index}] expected={normalized_expected} actual={normalized_actual}",
            )
    return True, "result_match_ok"


def _fail(
    name: str,
    reason: str,
    issue_tags: list[str],
    *,
    value: float = 0.0,
    review_required: bool = False,
    metadata: dict[str, Any] | None = None,
) -> EvalScoreDetail:
    """创建失败 detail，统一 value / tag / metadata 默认值。"""

    return EvalScoreDetail(
        name=name,
        value=value,
        passed=False,
        reason=reason,
        issue_tags=issue_tags,
        review_required=review_required,
        metadata=metadata or {},
    )
