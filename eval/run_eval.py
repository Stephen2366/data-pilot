"""M6 EvalOps-lite：读取 YAML 用例，调用 `/api/query`，输出 Markdown 评测报告。

★ 这个模块不是完整评测平台，而是阶段二收尾用的最小闭环：case -> API -> AgentResponse
-> pass/fail/error_type。后续接独立 AgentEvalOps 时，可以复用 YAML 字段和报告口径。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
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
    """一条 smoke case 的稳定结构，对应 `eval/cases_plan.md` 的 YAML 字段草案。"""

    case_id: str
    task_type: str
    question: str
    user_role: str
    expected_tables: list[str]
    expected_columns: list[str]
    security_expectation: Literal["allow", "block"]
    check_type: str
    check_value: str


@dataclass(frozen=True)
class EvalResult:
    """单条 case 的执行结果，Markdown 报告只消费这个结构。"""

    case: EvalCase
    passed: bool
    reason: str
    status_code: int
    route: str | None
    safety_status: str | None
    error_type: str | None
    trace_id: str | None
    sql: str | None
    response_body: dict[str, Any]


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[EvalCase]:
    """从 YAML 加载 smoke cases。

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
                security_expectation=item.get("security_expectation", "allow"),
                check_type=str(check.get("type", "contains")),
                check_value=str(check.get("value", "")),
            )
        )
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


def _score_case(case: EvalCase, body: dict[str, Any], status_code: int) -> tuple[bool, str]:
    """按 M6 最小评分规则判断单条 case。

    评分只覆盖接口成功、route、表/列命中、安全期望和简单内容检查；它故意不做复杂 SQL
    语义判等，避免阶段二收尾扩大成完整评测平台。
    """

    if status_code != 200:
        return False, f"http_status={status_code}"
    if body.get("route") != "sql":
        return False, f"route={body.get('route')}"

    safety_status = body.get("safety_status")
    if case.security_expectation == "block":
        if safety_status != "blocked":
            return False, f"safety_status={safety_status}"
        if case.check_type == "sql_guard_block" and not body.get("blocked_reason"):
            return False, "blocked_reason_empty"
        return True, "blocked_as_expected"

    if safety_status != "passed":
        return False, f"safety_status={safety_status}, error_type={body.get('error_type')}"

    actual_tables = set(body.get("tables_used") or [])
    missing_tables = [table for table in case.expected_tables if table not in actual_tables]
    if missing_tables:
        return False, f"missing_tables={missing_tables}"

    actual_columns = set(body.get("columns") or [])
    missing_columns = [column for column in case.expected_columns if column not in actual_columns]
    if missing_columns:
        return False, f"missing_columns={missing_columns}"

    text = _body_text(body)
    if case.check_type == "contains" and case.check_value not in text:
        return False, f"missing_text={case.check_value}"
    if case.check_type == "equals" and case.check_value not in text:
        return False, f"expected_value={case.check_value}"

    return True, "ok"


def run_cases(cases: list[EvalCase], client: TestClient) -> list[EvalResult]:
    """逐条调用 `/api/query` 并收集 pass / fail / error_type。"""

    results: list[EvalResult] = []
    for case in cases:
        response = client.post(
            "/api/query",
            json={"question": case.question, "user_role": case.user_role},
        )
        body = response.json()
        passed, reason = _score_case(case, body, response.status_code)
        results.append(
            EvalResult(
                case=case,
                passed=passed,
                reason=reason,
                status_code=response.status_code,
                route=body.get("route"),
                safety_status=body.get("safety_status"),
                error_type=body.get("error_type"),
                trace_id=body.get("trace_id"),
                sql=body.get("sql"),
                response_body=body,
            )
        )
    return results


def write_report(results: list[EvalResult], path: Path = DEFAULT_REPORT_PATH) -> None:
    """把评测结果写成 Markdown，方便 README / dev-log / 验收报告引用。"""

    passed_count = sum(result.passed for result in results)
    failed_count = len(results) - passed_count
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# DataPilot EvalOps-lite Latest Report",
        "",
        f"- generated_at: {generated_at}",
        f"- total: {len(results)}",
        f"- passed: {passed_count}",
        f"- failed: {failed_count}",
        "",
        "| id | type | pass | reason | safety | error_type | trace_id |",
        "|---|---|---:|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            "| {id} | {type} | {passed} | {reason} | {safety} | {error_type} | {trace_id} |".format(
                id=result.case.case_id,
                type=result.case.task_type,
                passed="yes" if result.passed else "no",
                reason=result.reason,
                safety=result.safety_status,
                error_type=result.error_type,
                trace_id=result.trace_id,
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
                f"- status_code: {result.status_code}",
                f"- route: {result.route}",
                f"- safety_status: {result.safety_status}",
                f"- error_type: {result.error_type}",
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
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE_PATH)
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    with seeded_api_client(args.trace) as client:
        results = run_cases(cases, client)
    write_report(results, args.report)

    passed_count = sum(result.passed for result in results)
    print(f"report={args.report}")
    print(f"trace_path={args.trace}")
    print(f"passed={passed_count}/{len(results)}")
    for result in results:
        print(
            f"{result.case.case_id}: passed={result.passed} reason={result.reason} "
            f"safety={result.safety_status} error_type={result.error_type} trace_id={result.trace_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
