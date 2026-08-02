"""M19 failure triage 测试：把失败 case 归因成可行动的阶段和动作。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.run_eval import EvalCase, EvalResult, write_report
from eval.scorers.base import EvalScoreDetail
from eval.triage import (
    build_triage_score_payloads,
    compare_triage_files,
    triage_results,
    write_triage_json,
)


def _case(**overrides: Any) -> EvalCase:
    """构造 M19 单测需要的最小 EvalCase。"""

    data = {
        "case_id": "m19_case",
        "task_type": "diagnostic",
        "question": "查询 2026 年 6 月 GMV",
        "user_role": "ops",
        "expected_tables": ["orders"],
        "expected_columns": ["gmv"],
        "expected_metrics": ["gmv"],
        "expected_trace_steps": [],
        "pipeline_mode": "new_text2sql",
        "security_expectation": "allow",
        "check_type": "expected_value",
        "check_value": "",
    }
    data.update(overrides)
    return EvalCase(**data)


def _result(**overrides: Any) -> EvalResult:
    """构造默认通过的 EvalResult，测试按需覆盖失败字段。"""

    data = {
        "case": _case(),
        "passed": True,
        "reason": "ok",
        "issue_tags": [],
        "review_required": False,
        "skipped_due_to_pipeline_mode": False,
        "status_code": 200,
        "route": "sql",
        "safety_status": "passed",
        "error_type": None,
        "trace_id": "datapilot-trace-1",
        "sql": "SELECT 1",
        "response_body": {"route": "sql", "safety_status": "passed"},
        "actual_pipeline_mode": "new_text2sql",
        "score_details": [EvalScoreDetail(name="rule:expected_value", value=1.0, passed=True, reason="ok")],
    }
    data.update(overrides)
    return EvalResult(**data)


def _write_trace(path: Path, *, trace_id: str = "datapilot-trace-1", **overrides: Any) -> None:
    """写一行最小 JSONL trace。"""

    record = {
        "trace_id": trace_id,
        "langfuse_trace_id": "lf-trace-1",
        "langfuse_write_status": "ok",
        "trace_steps": [],
    }
    record.update(overrides)
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def test_triage_classifies_sql_guard_from_failed_trace_step(tmp_path: Path) -> None:
    """SQL Guard 类失败应归到 `sql_guard`，下一步动作是修 pipeline / 安全边界。"""

    trace_path = tmp_path / "guard.jsonl"
    _write_trace(
        trace_path,
        trace_steps=[
            {
                "name": "sql_guard",
                "step_type": "sql_guard",
                "status": "blocked",
                "error_type": "sql_guard_blocked",
            }
        ],
    )
    result = _result(
        passed=False,
        reason="safety_status=passed",
        issue_tags=["safety_mismatch"],
        safety_status="passed",
        score_details=[
            EvalScoreDetail(
                name="rule:safety_compliance",
                value=0.0,
                passed=False,
                reason="safety_status=passed",
                issue_tags=["safety_mismatch"],
            )
        ],
    )

    triage = triage_results([result], trace_path=trace_path)[0]

    assert triage.failure_stage == "sql_guard"
    assert triage.needs_action == "fix_pipeline"
    assert triage.evidence_step == "trace:sql_guard"


def test_triage_classifies_sql_execution_from_error_type(tmp_path: Path) -> None:
    """SQL 执行错误即使没有 trace_steps，也能从 error_type 归因。"""

    trace_path = tmp_path / "execution.jsonl"
    _write_trace(trace_path, error_type="sql_execution_error")
    result = _result(
        passed=False,
        reason="error_type=sql_execution_error",
        issue_tags=["unexpected_error"],
        error_type="sql_execution_error",
        score_details=[
            EvalScoreDetail(
                name="rule:sql_success",
                value=0.0,
                passed=False,
                reason="error_type=sql_execution_error",
                issue_tags=["unexpected_error"],
            )
        ],
    )

    triage = triage_results([result], trace_path=trace_path)[0]

    assert triage.failure_stage == "sql_execution"
    assert triage.needs_action == "fix_pipeline"
    assert triage.confidence == 0.9


def test_report_includes_result_match_triage_summary(tmp_path: Path) -> None:
    """Markdown report 要包含 M19 Failure Triage Summary 和 case 明细。"""

    trace_path = tmp_path / "result-match.jsonl"
    _write_trace(trace_path)
    result = _result(
        passed=False,
        reason="result_mismatch row_count expected=2 actual=1",
        issue_tags=["result_mismatch"],
        score_details=[
            EvalScoreDetail(
                name="rule:result_match",
                value=0.0,
                passed=False,
                reason="result_mismatch row_count expected=2 actual=1",
                issue_tags=["result_mismatch"],
            )
        ],
    )
    triages = triage_results([result], trace_path=trace_path)
    report_path = tmp_path / "report.md"

    write_report(
        [result],
        report_path,
        triages=triages,
        langfuse_triage_write_result={"ok": 4, "skipped": 0, "failed": 0},
    )
    report = report_path.read_text(encoding="utf-8")

    assert "## Failure Triage Summary" in report
    assert "| result_match | 1 |" in report
    assert "| fix_pipeline | 1 |" in report
    assert "rule:result_match" in report
    assert "LangFuse Triage Score Write" in report


def test_triage_payloads_only_use_ok_langfuse_mapping(tmp_path: Path) -> None:
    """只有 JSONL 中确认写入 ok 的 LangFuse trace 才能回写 triage scores。"""

    ok_trace_path = tmp_path / "ok.jsonl"
    failed_trace_path = tmp_path / "failed.jsonl"
    _write_trace(ok_trace_path)
    _write_trace(failed_trace_path, langfuse_write_status="failed")
    result = _result(
        passed=False,
        score_details=[
            EvalScoreDetail(name="rule:result_match", value=0.0, passed=False, reason="result_mismatch")
        ],
    )

    ok_payloads = build_triage_score_payloads(triage_results([result], trace_path=ok_trace_path))
    failed_payloads = build_triage_score_payloads(triage_results([result], trace_path=failed_trace_path))

    assert [payload.name for payload in ok_payloads] == [
        "triage:failed",
        "triage:failure_stage",
        "triage:needs_action",
        "triage:confidence",
    ]
    assert ok_payloads[1].data_type == "CATEGORICAL"
    assert failed_payloads == []


def test_compare_triage_files_outputs_failure_distribution(tmp_path: Path) -> None:
    """本地 A/B 对比只比较 triage JSON，不触碰 LangFuse Dataset 或正式 case。"""

    left_json = tmp_path / "left.json"
    right_json = tmp_path / "right.json"
    output = tmp_path / "compare.md"
    left_result = _result(
        passed=False,
        trace_id="left-trace",
        score_details=[EvalScoreDetail(name="rule:table_hit", value=0.0, passed=False, reason="missing_tables")],
    )
    right_result = _result(
        passed=False,
        trace_id="right-trace",
        score_details=[EvalScoreDetail(name="rule:result_match", value=0.0, passed=False, reason="result_mismatch")],
    )
    left_trace = tmp_path / "left-trace.jsonl"
    right_trace = tmp_path / "right-trace.jsonl"
    _write_trace(left_trace, trace_id="left-trace")
    _write_trace(right_trace, trace_id="right-trace")
    write_triage_json(triage_results([left_result], trace_path=left_trace), left_json)
    write_triage_json(triage_results([right_result], trace_path=right_trace), right_json)

    compare_triage_files(left_path=left_json, right_path=right_json, output_path=output)
    report = output.read_text(encoding="utf-8")

    assert "| schema_retrieval | 1 | 0 | -1 |" in report
    assert "| result_match | 0 | 1 | 1 |" in report
