"""M17 L1/L2 规则评分器：DataPilot eval 的单一事实源。

本文件承接 `eval.run_eval._score_case()` 里原本分散的规则判断。原则是：能用确定性规则判断
的，就不要调 LLM；Markdown 报告和 LangFuse Score 回写都消费这里产出的同一批 detail。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime
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

    # ★ “期望阻断”与普通 allow / block 安全策略不同：它是产品能力边界，必须优先评分。
    if case.check_type == "plan_validation_blocked":
        return [_score_plan_validation_blocked(case, body)]

    safety_detail = _score_safety(case, body)
    details.append(safety_detail)
    if safety_detail.passed is False:
        return details
    if case.security_expectation == "block":
        return details

    # ★ 计划阻断和局部 Schema 上下文是过程契约，不能被最终 SQL 的表/列检查抢先遮蔽。
    # 否则“正确拒绝 supplier_name”会因为响应本来没有 supplier_name 而被误报成输出列失败。
    if case.check_type in {"schema_context_size", "schema_context_match"}:
        details.append(_score_schema_context(case, body))
        details.append(_score_sql_success(body))
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


def _score_plan_validation_blocked(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """评分“应结构化拒绝”的契约，并保留拒绝来源供 triage 区分语义/传输失败。"""

    trace_steps = body.get("_trace_steps") or []
    validation_step = next((step for step in trace_steps if step.get("step_type") == "plan_validation"), {})
    metadata = validation_step.get("metadata") or {}
    issue_tags = list(metadata.get("issue_tags") or body.get("issue_tags") or [])
    blocked_via = str(metadata.get("blocked_via") or "")
    accept_paths = list(case.check.get("accept_paths") or [])
    expected_tags = [str(case.check.get("expected_issue_tag") or case.expected_issue_tag)]
    expected_tags.extend(str(path.get("expected_issue_tag")) for path in accept_paths if path.get("expected_issue_tag"))
    expected_tags = [tag for tag in expected_tags if tag]

    if body.get("safety_status") != "blocked":
        return _fail("rule:plan_validation_blocked", "plan_validation_not_blocked", ["plan_validation_not_blocked"])
    if body.get("error_type") == "llm_generation_error":
        return _fail("rule:plan_validation_blocked", "llm_generation_error_not_semantic_rejection", ["llm_generation_error"])
    if not any(tag in issue_tags for tag in expected_tags):
        return _fail(
            "rule:plan_validation_blocked",
            f"expected_issue_tags={expected_tags} actual_issue_tags={issue_tags}",
            ["plan_validation_issue_mismatch"],
        )
    # ★ issue tag 只能说明“为什么拒绝”，blocked_via 才说明“在哪个能力边界拒绝”。
    # accept_paths 已把二者成对声明，不能只因 tag 碰巧一致就把错误的拒绝来源判通过。
    if accept_paths and not any(
        blocked_via == str(path.get("via"))
        and str(path.get("expected_issue_tag")) in issue_tags
        for path in accept_paths
    ):
        return _fail(
            "rule:plan_validation_blocked",
            f"expected_accept_paths={accept_paths} actual_blocked_via={blocked_via} actual_issue_tags={issue_tags}",
            ["plan_validation_via_mismatch"],
        )
    return EvalScoreDetail(
        name="rule:plan_validation_blocked",
        value=1.0,
        passed=True,
        reason="plan_validation_blocked_ok",
        metadata={"issue_tags": issue_tags, "blocked_via": blocked_via or "plan_validation"},
    )


def _score_schema_context(case: Any, body: dict[str, Any]) -> EvalScoreDetail:
    """按 JSONL trace 的 SchemaGraph 元数据评分，绝不拿最终输出列冒充上下文。

    `schema_context_match` 的 multi-answer case 直接检查同一请求的 tables/fields/metrics，
    不再先走最终响应的 table/column scorer。这样“检索上下文正确、生成 SQL 错误”能保持为
    两条独立证据，也让 alternatives 真正成为可执行合同而非 YAML 装饰字段。
    """

    trace_steps = body.get("_trace_steps") or []
    context_step = next((step for step in trace_steps if step.get("step_type") == "schema_context"), None)
    if not context_step:
        return _fail("rule:schema_context", "schema_context_trace_missing", ["schema_context_trace_missing"])

    metadata = context_step.get("metadata") or {}
    actual_tables = set(metadata.get("tables") or [])
    actual_fields = set(metadata.get("fields") or [])
    actual_columns = {field.rsplit(".", 1)[-1] for field in actual_fields}
    actual_metrics = set(metadata.get("metrics") or [])
    contract = case.expected_schema_context
    missing_tables = [table for table in contract.get("must_include_tables", []) if table not in actual_tables]
    missing_columns = [column for column in contract.get("must_include_columns", []) if column not in actual_columns]
    missing_join_keys = [key for key in contract.get("must_include_join_keys", []) if key not in actual_columns]

    # warn 级约束不会把 case 判失败，但必须出现在评分明细里；否则 schema_context_ok 会被误读为
    # “上下文没有噪音”。未来若 case 明确标为 error，则复用同一份结构化信息转为硬失败。
    contract_warnings: list[str] = []
    contract_errors: list[str] = []
    max_tables = contract.get("max_tables") or {}
    if isinstance(max_tables, dict) and max_tables.get("value") is not None:
        max_table_value = int(max_tables["value"])
        if len(actual_tables) > max_table_value:
            message = f"max_tables_exceeded={len(actual_tables)}>{max_table_value}"
            (contract_warnings if max_tables.get("level", "error") == "warn" else contract_errors).append(message)

    forbidden_config = contract.get("must_not_include_tables") or {}
    if isinstance(forbidden_config, dict):
        forbidden_tables = list(forbidden_config.get("tables") or [])
        forbidden_level = str(forbidden_config.get("level", "error"))
    else:
        forbidden_tables = list(forbidden_config)
        forbidden_level = "error"
    forbidden_present = [table for table in forbidden_tables if table in actual_tables]
    if forbidden_present:
        message = f"must_not_include_tables_present={forbidden_present}"
        (contract_warnings if forbidden_level == "warn" else contract_errors).append(message)

    # 步骤 2：multi-answer alternatives 只消费 SchemaGraph ===============================
    alternative_failures: list[dict[str, Any]] = []
    alternatives = list(case.expected_tables_alternatives or [])
    if case.check_type == "schema_context_match":
        match_mode = str(case.check.get("match_mode") or "any_alternative")
        require_columns = bool(case.check.get("alternative_must_include_columns", True))
        if match_mode != "any_alternative":
            contract_errors.append(f"unsupported_alternative_match_mode={match_mode}")
        elif not alternatives:
            contract_errors.append("schema_context_alternatives_empty")
        else:
            matched = False
            for index, alternative in enumerate(alternatives, start=1):
                expected_alt_tables = set(alternative.get("tables") or [])
                required_columns = set(alternative.get("required_columns") or []) if require_columns else set()
                # 指标名（如 gmv）可以来自 SchemaGraph.metrics，而不要求伪装成物理字段。
                available_names = actual_columns | actual_metrics
                missing_alt_tables = sorted(expected_alt_tables - actual_tables)
                missing_alt_columns = sorted(required_columns - available_names)
                if not missing_alt_tables and not missing_alt_columns:
                    matched = True
                    break
                alternative_failures.append(
                    {
                        "alternative_index": index,
                        "missing_tables": missing_alt_tables,
                        "missing_columns_or_metrics": missing_alt_columns,
                    }
                )
            if not matched:
                contract_errors.append("schema_context_alternatives_no_match")

    if missing_tables or missing_columns or missing_join_keys or contract_errors:
        return _fail(
            "rule:schema_context",
            " ".join(
                [
                    f"missing_tables={missing_tables}",
                    f"missing_columns={missing_columns}",
                    f"missing_join_keys={missing_join_keys}",
                    *contract_errors,
                ]
            ),
            ["schema_context_missing"],
            metadata={
                "actual_tables": sorted(actual_tables),
                "actual_fields": sorted(actual_fields),
                "actual_metrics": sorted(actual_metrics),
                "contract_warnings": contract_warnings,
                "alternative_failures": alternative_failures,
            },
        )
    return EvalScoreDetail(
        name="rule:schema_context",
        value=1.0,
        passed=True,
        reason=("schema_context_ok" if not contract_warnings else f"schema_context_ok warnings={contract_warnings}"),
        metadata={
            "actual_tables": sorted(actual_tables),
            "actual_fields": sorted(actual_fields),
            "actual_metrics": sorted(actual_metrics),
            "contract_warnings": contract_warnings,
            "alternative_failures": alternative_failures,
        },
    )


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
    if case.check_type == "equals":
        actual_value = _resolve_equals_value(case, body)
        if actual_value != case.check_value:
            return _fail(
                "rule:equals",
                f"expected_value={case.check_value} actual={actual_value}",
                ["unexpected_error"],
                metadata={"field": case.check.get("field", "answer"), "actual": actual_value},
            )
        return EvalScoreDetail(
            name="rule:equals",
            value=1.0,
            passed=True,
            reason="equals_ok",
            metadata={"field": case.check.get("field", "answer")},
        )
    if case.check_type == "manual":
        return EvalScoreDetail(
            name="rule:manual_review",
            value=1.0,
            passed=True,
            reason="manual_review_required",
            review_required=True,
        )
    return EvalScoreDetail(name=f"rule:{case.check_type or 'default'}", value=1.0, passed=True, reason="ok")


def _resolve_equals_value(case: Any, body: dict[str, Any]) -> str:
    """解析 equals 的比较对象；默认只比较最终 answer，不再对整个 JSON 做 substring。"""

    field = str(case.check.get("field") or "answer")
    if field == "body_json":
        return _body_text(body)
    if field.startswith("rows[0]."):
        column = field.removeprefix("rows[0].")
        rows = body.get("rows") or []
        if rows and isinstance(rows[0], dict):
            value = rows[0].get(column)
            return "" if value is None else str(value)
        return ""
    value = body.get(field)
    return "" if value is None else str(value)


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
    """★ 执行 expected_sql，并校验精确投影 / 展示顺序与行值结果。"""

    if not case.expected_sql.strip():
        return _fail("rule:result_match", "result_match_expected_sql_empty", ["unexpected_error"])
    actual_columns = body.get("columns") or []
    if not isinstance(actual_columns, list):
        return _fail("rule:result_match", "result_match_actual_columns_invalid", ["unexpected_error"])
    # alias 白名单只消除“同义列名”噪声，不放宽多列、少列或顺序变化。
    canonical_columns = _canonicalize_column_aliases(actual_columns, case.expected_column_aliases)
    if canonical_columns != list(case.expected_columns):
        return _fail(
            "rule:result_match",
            f"result_projection_mismatch expected={list(case.expected_columns)} actual={canonical_columns}",
            ["output_projection_mismatch"],
            metadata={"expected_columns": list(case.expected_columns), "actual_columns": canonical_columns},
        )
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

    matched, reason = _rows_match(
        actual_rows=_canonicalize_row_aliases(actual_rows, case.expected_column_aliases),
        expected_rows=expected_rows,
        tolerance=tolerance,
        order_insensitive=bool(case.check.get("order_insensitive", False)),
    )
    if not matched:
        return _fail("rule:result_match", f"result_mismatch {reason}", ["result_mismatch"])
    return EvalScoreDetail(name="rule:result_match", value=1.0, passed=True, reason=reason)


def _canonicalize_row_aliases(rows: Sequence[dict[str, Any]], aliases: dict[str, list[str]]) -> list[dict[str, Any]]:
    """把 case 明示的等价输出别名归一到 reference 列名，避免 alias 白名单只对列检查生效。"""

    alias_to_canonical = {alias: canonical for canonical, names in aliases.items() for alias in names}
    return [{alias_to_canonical.get(key, key): value for key, value in row.items()} for row in rows]


def _canonicalize_column_aliases(columns: Sequence[str], aliases: dict[str, list[str]]) -> list[str]:
    """把展示列 alias 归一为 canonical 名，同时保留原顺序供精确投影合同判断。"""

    alias_to_canonical = {alias: canonical for canonical, names in aliases.items() for alias in names}
    return [alias_to_canonical.get(column, column) for column in columns]


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
    # SQL Tool 会把数据库日期时间序列化为 ISO 8601；reference SQL 则直接保留 SQLAlchemy
    # datetime。这里统一成同一格式，避免“结果相同、表示法不同”把列表 case 误判失败。
    if isinstance(value, datetime | date):
        return value.isoformat()
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)


def _row_sort_key(row: dict[str, Any]) -> tuple[str, ...]:
    """为无序比较生成稳定排序 key。"""

    return tuple(f"{key}={_normalize_result_value(value)}" for key, value in sorted(row.items()))


def _rows_match(
    *,
    actual_rows: Sequence[dict[str, Any]],
    expected_rows: Sequence[dict[str, Any]],
    tolerance: Decimal,
    order_insensitive: bool = False,
) -> tuple[bool, str]:
    """比较两组结果行；默认按列名对齐，必要时由 case 显式开启无序比较。"""

    if len(actual_rows) != len(expected_rows):
        return False, f"row_count expected={len(expected_rows)} actual={len(actual_rows)}"
    actual_sequence = sorted(actual_rows, key=_row_sort_key) if order_insensitive else list(actual_rows)
    expected_sequence = sorted(expected_rows, key=_row_sort_key) if order_insensitive else list(expected_rows)
    for row_index, (actual_row, expected_row) in enumerate(zip(actual_sequence, expected_sequence, strict=True)):
        actual_columns = set(actual_row)
        expected_columns = set(expected_row)
        if actual_columns != expected_columns:
            return (
                False,
                f"row[{row_index}] columns expected={sorted(expected_columns)} actual={sorted(actual_columns)}",
            )
        for column_name in expected_row:
            normalized_actual = _normalize_result_value(actual_row[column_name])
            normalized_expected = _normalize_result_value(expected_row[column_name])
            if isinstance(normalized_actual, Decimal) and isinstance(normalized_expected, Decimal):
                if abs(normalized_actual - normalized_expected) <= tolerance:
                    continue
            elif normalized_actual == normalized_expected:
                continue
            return (
                False,
                f"row[{row_index}] column={column_name} expected={normalized_expected} actual={normalized_actual}",
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
