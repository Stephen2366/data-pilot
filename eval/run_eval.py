"""EvalOps-lite：读取 YAML 用例，调用 `/api/query`，输出 Markdown 评测报告。

★ 这个模块不是完整评测平台，而是从阶段二 smoke 延伸到 Phase 3A diagnostic benchmark 的
最小闭环：case -> API -> AgentResponse -> pass/fail/skipped/error_type。M8.5 只补多文件合并、
pipeline_mode 覆盖和诊断报告字段，复杂 scorer / 历史库 / HTML 仪表盘仍留给独立 EvalOps。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database

DEFAULT_CASES_PATH = PROJECT_ROOT / "eval" / "cases" / "smoke.yaml"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "eval" / "reports" / "latest.md"
DEFAULT_TRACE_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m6-eval-traces.jsonl"


@dataclass(frozen=True)
class EvalCase:
    """一条 eval case 的稳定结构。

    ★ M8.5 起同一个 loader 同时服务 M6 smoke、Phase 3A regression 和 32 条 diagnostic：
    旧 smoke 字段不能被新字段反向绑架，新字段则先在数据结构里预留，方便 M9-M12 继续扩展。
    """

    case_id: str
    task_type: str
    question: str
    user_role: str
    expected_tables: list[str]
    expected_columns: list[str]
    expected_metrics: list[str]
    expected_trace_steps: list[Any]
    pipeline_mode: str
    security_expectation: Literal["allow", "block"]
    check_type: str
    check_value: str
    source_file: str = ""
    phase3a_capabilities: list[str] = field(default_factory=list)
    phase3a_blocking: bool = True
    case_properties: list[str] = field(default_factory=list)
    linked_case_id: str | None = None
    expected_tables_alternatives: list[dict[str, Any]] = field(default_factory=list)
    expected_plan: dict[str, Any] = field(default_factory=dict)
    expected_plan_result: str = ""
    expected_issue_tag: str = ""
    expected_schema_context: dict[str, Any] = field(default_factory=dict)
    expected_column_aliases: dict[str, list[str]] = field(default_factory=dict)
    security_subtype: str | None = None
    expected_sql: str = ""
    check: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalScore:
    """评分函数的结构化输出。

    reason 给人读，issue_tags 给后续报告 / 对照脚本稳定消费；M8 只落最小标签集合，不提前做
    完整 scorer 平台。
    """

    passed: bool
    reason: str
    issue_tags: list[str]
    review_required: bool = False
    skipped_due_to_pipeline_mode: bool = False


@dataclass(frozen=True)
class EvalResult:
    """单条 case 的执行结果，Markdown 报告只消费这个结构。"""

    case: EvalCase
    passed: bool
    reason: str
    issue_tags: list[str]
    review_required: bool
    skipped_due_to_pipeline_mode: bool
    status_code: int
    route: str | None
    safety_status: str | None
    error_type: str | None
    trace_id: str | None
    sql: str | None
    response_body: dict[str, Any]
    actual_pipeline_mode: str


# 旧 baseline 无法真实验证的新链路检查类型。
#
# 这些 check 依赖 M9-M11 才会出现的 QueryPlan、局部 Schema 或 trace_steps。M8.5 如果硬判
# 失败，会把“能力尚未实现”和“旧链路答错了”混在一起；硬判通过又会虚报能力，所以单独记 skipped。
NEW_PIPELINE_ONLY_CHECKS = {
    "plan_structure_match",
    "plan_validation_blocked",
    "schema_context_match",
    "schema_context_size",
    "trace_steps_complete",
}


def _source_file_label(path: Path) -> str:
    """把 case 来源路径转成报告里稳定、跨机器可读的相对路径。"""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name


def _load_cases_from_path(path: Path) -> list[EvalCase]:
    """从单个 YAML 加载 cases，并把 M8.5 诊断字段保留下来。

    ★ 这里做轻量结构化转换，不重新定义字段口径；如果 YAML 缺字段，直接抛错提醒用例不完整。
    """

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[EvalCase] = []
    for item in payload.get("cases") or []:
        check = item.get("check") or {}
        cases.append(
            EvalCase(
                case_id=str(item["id"]),
                task_type=str(item["task_type"]),
                question=str(item["question"]),
                user_role=str(item.get("user_role", "ops")),
                expected_tables=list(item.get("expected_tables") or []),
                expected_columns=list(item.get("expected_columns") or []),
                expected_metrics=list(item.get("expected_metrics") or []),
                expected_trace_steps=list(item.get("expected_trace_steps") or []),
                pipeline_mode=str(item.get("pipeline_mode", "baseline")),
                security_expectation=item.get("security_expectation", "allow"),
                check_type=str(check.get("type", "contains")),
                check_value=str(check.get("value", "")),
                source_file=_source_file_label(path),
                phase3a_capabilities=list(item.get("phase3a_capabilities") or []),
                phase3a_blocking=bool(item.get("phase3a_blocking", True)),
                case_properties=list(item.get("case_properties") or []),
                linked_case_id=item.get("linked_case_id"),
                expected_tables_alternatives=list(item.get("expected_tables_alternatives") or []),
                expected_plan=dict(item.get("expected_plan") or {}),
                expected_plan_result=str(item.get("expected_plan_result", "")),
                expected_issue_tag=str(item.get("expected_issue_tag", "")),
                expected_schema_context=dict(item.get("expected_schema_context") or {}),
                expected_column_aliases={
                    str(column): [str(alias) for alias in aliases]
                    for column, aliases in dict(item.get("expected_column_aliases") or {}).items()
                },
                security_subtype=item.get("security_subtype"),
                expected_sql=str(item.get("expected_sql", "")),
                check=dict(check),
            )
        )
    return cases


def load_cases(path: Path = DEFAULT_CASES_PATH, extra_cases: list[Path] | None = None) -> list[EvalCase]:
    """加载主 case 文件，并可按顺序合并额外 case 文件。

    ★ M8.5 不做 includes 语法，保持显式 `--cases + --extra-cases`：调用者一眼能看出
    32 条 diagnostic benchmark 是由哪两个文件拼出来的。
    """

    paths = [path, *(extra_cases or [])]
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for case_path in paths:
        for case in _load_cases_from_path(case_path):
            if case.case_id in seen_ids:
                raise ValueError(f"duplicate eval case id: {case.case_id}")
            seen_ids.add(case.case_id)
            cases.append(case)
    return cases


def _prepare_sqlite_seed() -> Any:
    """创建带 M1 确定性 seed 的内存 SQLite engine。

    Eval 默认不碰 MySQL 开发库，避免“跑评测”变成隐式写库操作；但 API seam 仍然是真实
    `/api/query`，只是数据库依赖在进程内被 FastAPI 覆盖。
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
    return engine


@contextmanager
def seeded_api_client(trace_path: Path = DEFAULT_TRACE_PATH) -> Generator[TestClient, None, None]:
    """返回一个连接内存 seed 数据库的 FastAPI TestClient。"""

    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")
    engine = _prepare_sqlite_seed()

    def override_get_db() -> Generator[Session, None, None]:
        """把正式数据库 Session 替换成内存 SQLite Session。"""

        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(engine)


def _body_text(body: dict[str, Any]) -> str:
    """把响应体转成稳定字符串，供 contains / equals 轻量评分使用。"""

    return json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)


def _score_expected_value(case: EvalCase, body: dict[str, Any]) -> EvalScore:
    """按固定事实数值检查首行结果，先解决 GMV=NULL 被误判通过的问题。"""

    field_name = str(case.check.get("field") or "").strip()
    if not field_name:
        return EvalScore(False, "expected_value_field_empty", ["unexpected_error"])

    rows = body.get("rows") or []
    if not rows or not isinstance(rows[0], dict):
        return EvalScore(False, f"expected_value_missing_row field={field_name}", ["unexpected_error"])

    row = rows[0]
    actual_field_name = field_name
    actual_value = row.get(field_name)
    if actual_value is None:
        for alias in case.expected_column_aliases.get(field_name, []):
            if alias in row:
                actual_field_name = alias
                actual_value = row.get(alias)
                break
    # ★ 单指标固定事实题只返回一列时，列名常被 LLM 写成中文业务标题；
    # 此时继续卡列名会误杀正确数值，所以让 Decimal 数值校验承担最终判断。
    if actual_value is None and len(row) == 1:
        actual_field_name, actual_value = next(iter(row.items()))
    if actual_value is None:
        return EvalScore(False, f"expected_value field={field_name} actual=NULL", ["unexpected_error"])

    try:
        expected = Decimal(str(case.check.get("value")))
        actual = Decimal(str(actual_value))
        tolerance = Decimal(str(case.check.get("tolerance", "0")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        return EvalScore(False, f"expected_value_invalid_number field={field_name}: {exc}", ["unexpected_error"])

    if abs(actual - expected) > tolerance:
        return EvalScore(
            False,
            f"expected_value field={actual_field_name} expected={expected} actual={actual} tolerance={tolerance}",
            ["unexpected_error"],
        )
    return EvalScore(True, "expected_value_ok", [])


def _should_skip_due_to_pipeline_mode(case: EvalCase, actual_pipeline_mode: str) -> bool:
    """判断旧链路是否无法验证这条 case 的核心检查。

    M8.5 的核心边界是“先把诊断骨架落地”，不是让旧 pipeline 硬装成新 pipeline。plan、
    trace_steps、local schema 这些字段只有 M9-M11 后才有真实证据，所以 baseline 下只能记
    skipped，不能算失败或成功。
    """

    if actual_pipeline_mode != "baseline":
        return False
    if case.check_type in NEW_PIPELINE_ONLY_CHECKS:
        return True
    return bool(case.expected_plan or case.expected_schema_context or case.expected_trace_steps)


def _score_case(
    case: EvalCase,
    body: dict[str, Any],
    status_code: int,
    actual_pipeline_mode: str | None = None,
) -> EvalScore:
    """按 EvalOps-lite 最小评分规则判断单条 case。

    评分只覆盖接口成功、route、表/列命中、安全期望和简单内容检查；它故意不做复杂 SQL
    语义判等，避免 M8 baseline 扩大成完整评测平台。
    """

    actual_mode = actual_pipeline_mode or case.pipeline_mode
    if _should_skip_due_to_pipeline_mode(case, actual_mode):
        return EvalScore(
            False,
            "skipped_due_to_pipeline_mode",
            ["skipped_due_to_pipeline_mode"],
            skipped_due_to_pipeline_mode=True,
        )

    if status_code != 200:
        return EvalScore(False, f"http_status={status_code}", ["unexpected_error"])
    if body.get("route") != "sql":
        return EvalScore(False, f"route={body.get('route')}", ["unexpected_error"])

    safety_status = body.get("safety_status")
    if case.security_expectation == "block":
        if safety_status != "blocked":
            return EvalScore(False, f"safety_status={safety_status}", ["safety_mismatch"])
        if case.check_type == "sql_guard_block" and not body.get("blocked_reason"):
            return EvalScore(False, "blocked_reason_empty", ["safety_mismatch"])
        return EvalScore(True, "blocked_as_expected", [])

    if safety_status != "passed":
        tag = "unexpected_error" if body.get("error_type") else "safety_mismatch"
        return EvalScore(
            False,
            f"safety_status={safety_status}, error_type={body.get('error_type')}",
            [tag],
            review_required=case.check_type == "manual",
        )

    actual_tables = set(body.get("tables_used") or [])
    missing_tables = [table for table in case.expected_tables if table not in actual_tables]
    if missing_tables:
        return EvalScore(
            False,
            f"missing_tables={missing_tables}",
            ["missing_table"],
            review_required=case.check_type == "manual",
        )

    actual_columns = set(body.get("columns") or [])
    missing_columns = [
        column
        for column in case.expected_columns
        if column not in actual_columns
        and not any(alias in actual_columns for alias in case.expected_column_aliases.get(column, []))
    ]
    if (
        missing_columns
        and case.check_type == "expected_value"
        and len(case.expected_columns) == 1
        and len(actual_columns) == 1
    ):
        # ★ 和 `_score_expected_value()` 的单列兜底保持一致：先别因别名失败短路。
        missing_columns = []
    if missing_columns:
        return EvalScore(
            False,
            f"missing_columns={missing_columns}",
            ["missing_column"],
            review_required=case.check_type == "manual",
        )

    text = _body_text(body)
    if case.check_type == "expected_value":
        return _score_expected_value(case, body)
    if case.check_type == "contains" and case.check_value not in text:
        return EvalScore(False, f"missing_text={case.check_value}", ["unexpected_error"])
    if case.check_type == "equals" and case.check_value not in text:
        return EvalScore(False, f"expected_value={case.check_value}", ["unexpected_error"])
    if case.check_type == "manual":
        return EvalScore(True, "manual_review_required", [], review_required=True)

    return EvalScore(True, "ok", [])


def run_cases(
    cases: list[EvalCase],
    client: TestClient,
    pipeline_mode: str | None = None,
) -> list[EvalResult]:
    """逐条调用 `/api/query` 并收集 pass / fail / error_type。"""

    results: list[EvalResult] = []
    for case in cases:
        actual_pipeline_mode = pipeline_mode or case.pipeline_mode
        if _should_skip_due_to_pipeline_mode(case, actual_pipeline_mode):
            score = _score_case(case, {}, 0, actual_pipeline_mode=actual_pipeline_mode)
            results.append(
                EvalResult(
                    case=case,
                    passed=score.passed,
                    reason=score.reason,
                    issue_tags=score.issue_tags,
                    review_required=score.review_required,
                    skipped_due_to_pipeline_mode=score.skipped_due_to_pipeline_mode,
                    status_code=0,
                    route=None,
                    safety_status=None,
                    error_type=None,
                    trace_id=None,
                    sql=None,
                    response_body={},
                    actual_pipeline_mode=actual_pipeline_mode,
                )
            )
            continue

        request_body: dict[str, Any] = {"question": case.question, "user_role": case.user_role}
        if actual_pipeline_mode != "baseline":
            request_body["force_new_pipeline"] = True
        response = client.post(
            "/api/query",
            json=request_body,
        )
        body = response.json()
        score = _score_case(case, body, response.status_code, actual_pipeline_mode=actual_pipeline_mode)
        results.append(
            EvalResult(
                case=case,
                passed=score.passed,
                reason=score.reason,
                issue_tags=score.issue_tags,
                review_required=score.review_required,
                skipped_due_to_pipeline_mode=score.skipped_due_to_pipeline_mode,
                status_code=response.status_code,
                route=body.get("route"),
                safety_status=body.get("safety_status"),
                error_type=body.get("error_type"),
                trace_id=body.get("trace_id"),
                sql=body.get("sql"),
                response_body=body,
                actual_pipeline_mode=actual_pipeline_mode,
            )
        )
    return results


def write_report(results: list[EvalResult], path: Path = DEFAULT_REPORT_PATH) -> None:
    """把评测结果写成 Markdown，方便 README / dev-log / 验收报告引用。"""

    passed_count = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in results)
    skipped_count = sum(result.skipped_due_to_pipeline_mode for result in results)
    failed_count = len(results) - passed_count - skipped_count
    review_count = sum(result.review_required for result in results)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# DataPilot EvalOps-lite Latest Report",
        "",
        f"- generated_at: {generated_at}",
        f"- total: {len(results)}",
        f"- passed: {passed_count}",
        f"- failed: {failed_count}",
        f"- skipped_due_to_pipeline_mode: {skipped_count}",
        f"- review_required: {review_count}",
        "",
        "## Blocking Summary",
        "",
        "| group | total | passed | failed | skipped | review_required |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, expected_blocking in [("blocking", True), ("non_blocking", False)]:
        group = [result for result in results if result.case.phase3a_blocking is expected_blocking]
        group_passed = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in group)
        group_skipped = sum(result.skipped_due_to_pipeline_mode for result in group)
        group_failed = len(group) - group_passed - group_skipped
        group_review = sum(result.review_required for result in group)
        lines.append(f"| {label} | {len(group)} | {group_passed} | {group_failed} | {group_skipped} | {group_review} |")

    capability_names = sorted(
        {
            capability
            for result in results
            for capability in result.case.phase3a_capabilities
        }
    )
    if capability_names:
        lines.extend(
            [
                "",
                "## Capability Summary",
                "",
                "| capability | coverage | passed | failed | skipped | review_required |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for capability in capability_names:
            group = [result for result in results if capability in result.case.phase3a_capabilities]
            group_passed = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in group)
            group_skipped = sum(result.skipped_due_to_pipeline_mode for result in group)
            group_failed = len(group) - group_passed - group_skipped
            group_review = sum(result.review_required for result in group)
            lines.append(
                f"| {capability} | {len(group)} | {group_passed} | {group_failed} | {group_skipped} | {group_review} |"
            )

    lines.extend(
        [
            "",
            "## Case Summary",
            "",
            "| id | type | pass | skipped | reason | issue_tags | review_required | safety | error_type | trace_id | source_file | configured_pipeline_mode | actual_pipeline_mode | phase3a_blocking | capabilities |",
            "|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        lines.append(
            "| {id} | {type} | {passed} | {skipped} | {reason} | {issue_tags} | {review_required} | {safety} | {error_type} | {trace_id} | {source_file} | {configured_pipeline_mode} | {actual_pipeline_mode} | {blocking} | {capabilities} |".format(
                id=result.case.case_id,
                type=result.case.task_type,
                passed="yes" if result.passed else "no",
                skipped="yes" if result.skipped_due_to_pipeline_mode else "no",
                reason=result.reason,
                issue_tags=",".join(result.issue_tags) or "-",
                review_required="yes" if result.review_required else "no",
                safety=result.safety_status,
                error_type=result.error_type,
                trace_id=result.trace_id,
                source_file=result.case.source_file,
                configured_pipeline_mode=result.case.pipeline_mode,
                actual_pipeline_mode=result.actual_pipeline_mode,
                blocking="yes" if result.case.phase3a_blocking else "no",
                capabilities=",".join(result.case.phase3a_capabilities) or "-",
            )
        )
    lines.extend(["", "## Case Details", ""])
    for result in results:
        sql = result.sql or ""
        lines.extend(
            [
                f"### {result.case.case_id} {result.case.question}",
                "",
                f"- user_role: {result.case.user_role}",
                f"- source_file: {result.case.source_file}",
                f"- configured_pipeline_mode: {result.case.pipeline_mode}",
                f"- actual_pipeline_mode: {result.actual_pipeline_mode}",
                f"- phase3a_capabilities: {', '.join(result.case.phase3a_capabilities) or '-'}",
                f"- phase3a_blocking: {'yes' if result.case.phase3a_blocking else 'no'}",
                f"- case_properties: {', '.join(result.case.case_properties) or '-'}",
                f"- security_subtype: {result.case.security_subtype or '-'}",
                f"- expected_metrics: {', '.join(result.case.expected_metrics) or '-'}",
                f"- status_code: {result.status_code}",
                f"- route: {result.route}",
                f"- safety_status: {result.safety_status}",
                f"- error_type: {result.error_type}",
                f"- issue_tags: {', '.join(result.issue_tags) or '-'}",
                f"- review_required: {'yes' if result.review_required else 'no'}",
                f"- skipped_due_to_pipeline_mode: {'yes' if result.skipped_due_to_pipeline_mode else 'no'}",
                f"- trace_id: {result.trace_id}",
                "",
                "```sql",
                sql.replace("`", ""),
                "```",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """命令行入口：加载 cases，执行 API smoke，并写入 latest.md。"""

    parser = argparse.ArgumentParser(description="Run DataPilot M6 EvalOps-lite smoke cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--extra-cases", type=Path, action="append", default=[])
    parser.add_argument("--pipeline-mode", choices=["baseline", "new_text2sql"], default=None)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE_PATH)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases, extra_cases=args.extra_cases)
    with seeded_api_client(args.trace) as client:
        results = run_cases(cases, client, pipeline_mode=args.pipeline_mode)
    write_report(results, args.report)

    passed_count = sum(result.passed and not result.skipped_due_to_pipeline_mode for result in results)
    skipped_count = sum(result.skipped_due_to_pipeline_mode for result in results)
    print(f"report={args.report}")
    print(f"trace_path={args.trace}")
    print(f"passed={passed_count}/{len(results)}")
    print(f"skipped_due_to_pipeline_mode={skipped_count}/{len(results)}")
    for result in results:
        print(
            f"{result.case.case_id}: passed={result.passed} reason={result.reason} "
            f"issue_tags={','.join(result.issue_tags) or '-'} review_required={result.review_required} "
            f"skipped_due_to_pipeline_mode={result.skipped_due_to_pipeline_mode} "
            f"actual_pipeline_mode={result.actual_pipeline_mode} "
            f"safety={result.safety_status} "
            f"error_type={result.error_type} trace_id={result.trace_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
