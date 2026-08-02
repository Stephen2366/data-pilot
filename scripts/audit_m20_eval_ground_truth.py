"""M20 eval ground-truth audit.

这个脚本只做只读审查：加载 formal / challenge / diagnostic 三类 case，统计 case 结构，
并用当前配置数据库执行 `expected_sql`。它不改变 scorer 口径，也不写正式报告；输出给
`.agent_work/temp/m20-eval-ground-truth-audit.md`，作为 M20 判断“标准答案是否可信”的素材。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from eval.run_eval import EvalCase, load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORMAL_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
DIAGNOSTIC_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"
DEFAULT_OUTPUT = PROJECT_ROOT / ".agent_work" / "temp" / "m20-eval-ground-truth-audit.md"


def _format_value(value: Any) -> str:
    """把 SQL 结果压成 Markdown 友好的短文本，避免 Decimal / datetime 展示不稳定。"""

    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _preview_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> str:
    """只展示前几行，审计文件关注可执行性和固定事实，不承载完整 SQL dump。"""

    if not rows:
        return "[]"
    preview = []
    for row in rows[:limit]:
        preview.append("{" + ", ".join(f"{key}={_format_value(value)}" for key, value in row.items()) + "}")
    suffix = "" if len(rows) <= limit else f" ... total={len(rows)}"
    return "; ".join(preview) + suffix


def _execute_expected_sql(cases: list[EvalCase]) -> list[dict[str, Any]]:
    """在当前 configured database 上执行每条 expected SQL。"""

    settings = get_settings()
    engine = create_engine(settings.database_url)
    rows: list[dict[str, Any]] = []
    try:
        with Session(engine) as session:
            for case in cases:
                if not case.expected_sql.strip():
                    continue
                try:
                    result = session.execute(text(case.expected_sql))
                    result_rows = [dict(row) for row in result.mappings().all()]
                    rows.append(
                        {
                            "case_id": case.case_id,
                            "source_file": case.source_file,
                            "status": "ok",
                            "row_count": len(result_rows),
                            "preview": _preview_rows(result_rows),
                            "error": "",
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - 审计报告需要保留数据库真实错误。
                    rows.append(
                        {
                            "case_id": case.case_id,
                            "source_file": case.source_file,
                            "status": "error",
                            "row_count": 0,
                            "preview": "",
                            "error": str(exc).replace("\n", " "),
                        }
                    )
    finally:
        engine.dispose()
    return rows


def build_audit_markdown() -> str:
    """生成 M20 ground-truth audit Markdown。"""

    formal = load_cases(FORMAL_CASES)
    challenge = load_cases(CHALLENGE_CASES)
    diagnostic_extra = load_cases(DIAGNOSTIC_CASES)
    all_cases = [*formal, *challenge, *diagnostic_extra]
    id_counts = Counter(case.case_id for case in all_cases)
    duplicate_ids = sorted(case_id for case_id, count in id_counts.items() if count > 1)
    check_counts = Counter(case.check_type for case in all_cases)
    expected_sql_cases = [case for case in all_cases if case.expected_sql.strip()]
    sql_audit_rows = _execute_expected_sql(expected_sql_cases)
    sql_errors = [row for row in sql_audit_rows if row["status"] != "ok"]

    lines = [
        "# M20 Eval Ground Truth Audit",
        "",
        f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- configured_database_url: {get_settings().database_url.split('@')[-1] if '@' in get_settings().database_url else get_settings().database_url}",
        "- oracle_backend_for_current_result_match: SQLite deterministic seed (`eval.scorers.rule_scorers._prepare_sqlite_seed`)",
        "- M20_decision: do not switch result_match oracle to MySQL in this module; this file records the MySQL audit baseline.",
        "",
        "## Case Counts",
        "",
        "| suite | count |",
        "|---|---:|",
        f"| formal | {len(formal)} |",
        f"| challenge | {len(challenge)} |",
        f"| diagnostic_extra | {len(diagnostic_extra)} |",
        f"| total_loaded_separately | {len(all_cases)} |",
        "",
        f"- duplicate_case_ids_across_files: {', '.join(duplicate_ids) if duplicate_ids else '-'}",
        "",
        "## Check Type Counts",
        "",
        "| check_type | count |",
        "|---|---:|",
    ]
    for check_type, count in sorted(check_counts.items()):
        lines.append(f"| {check_type} | {count} |")

    lines.extend(
        [
            "",
            "## Expected SQL Execution On Configured MySQL",
            "",
            f"- expected_sql_cases: {len(expected_sql_cases)}",
            f"- ok: {len(sql_audit_rows) - len(sql_errors)}",
            f"- error: {len(sql_errors)}",
            "",
            "| case_id | source_file | status | row_count | preview_or_error |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in sql_audit_rows:
        preview_or_error = row["preview"] if row["status"] == "ok" else row["error"]
        lines.append(
            f"| {row['case_id']} | {row['source_file']} | {row['status']} | {row['row_count']} | {preview_or_error} |"
        )

    lines.extend(
        [
            "",
            "## Known Case Hygiene Notes",
            "",
            "- `result_match` currently uses SQLite deterministic seed as the oracle, not the configured MySQL database.",
            "- Formal multi-table cases with `contains` checks may be too weak for long-term benchmark use; M20 records this but does not change YAML.",
            "- `db_core_002` refund-rate wording and `db_simple_002` paid-order wording remain unchanged in M20; both need a separate benchmark口径 decision before edits.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    """CLI 入口。"""

    DEFAULT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT.write_text(build_audit_markdown(), encoding="utf-8")
    print(f"audit={DEFAULT_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
