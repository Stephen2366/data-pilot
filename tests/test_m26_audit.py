"""M26 audit seam 的确定性测试：只消费 fixture，不调用 LLM 或真实数据库。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.audit import apply_audit_verdicts, build_audit_records, summarize_reconciliation
from eval.run_eval import EvalCase


def _case(case_id: str, *, check_type: str = "contains", check: dict[str, object] | None = None) -> EvalCase:
    """构造最小 EvalCase；测试关注 M26 组装，不复制完整 YAML。"""

    return EvalCase(
        case_id=case_id,
        task_type="sql",
        question=f"question-{case_id}",
        user_role="ops",
        expected_tables=["products"],
        expected_columns=["product_name"],
        expected_metrics=[],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type=check_type,
        check_value="ok",
        semantic_group_id=f"group-{case_id}",
        check=check or {"type": check_type, "value": "ok"},
    )


def _trace(case: EvalCase, *, trace_id: str, mode: str) -> dict[str, object]:
    """构造 normal/timeout/guard 三种 pipeline 结果，覆盖 P0 的关键 SQL 状态分支。"""

    base: dict[str, object] = {
        "trace_id": trace_id,
        "question": case.question,
        "route": "sql",
        "answer": "ok",
        "sql": "SELECT product_name FROM products",
        "columns": ["product_name"],
        "rows": [{"product_name": "demo"}],
        "safety_status": "passed",
        "error_type": None,
    }
    if mode == "timeout":
        base.update({"route": None, "sql": None, "rows": [], "safety_status": "blocked", "error_type": "llm_generation_error"})
        steps = [{"name": "query_plan", "step_type": "query_plan", "status": "error", "error_type": "llm_generation_error", "metadata": {"llm_call": {"attempts": [{"error_subtype": "timeout"}]}}}]
    elif mode == "guard":
        base.update({"safety_status": "blocked", "error_type": "sql_guard_blocked"})
        steps = [{"name": "sql_guard", "step_type": "sql_guard", "status": "blocked", "error_type": "sql_guard_blocked", "metadata": {"blocked_reason": "fixture"}}]
    else:
        steps = [
            {"name": "schema_retrieval", "step_type": "schema_retrieval", "status": "success", "metadata": {"top_doc_ids": ["field:products.product_name"]}},
            {"name": "schema_context", "step_type": "schema_context", "status": "success", "metadata": {"tables": ["products"], "fields": ["products.product_name"]}},
            {"name": "sql_generation", "step_type": "sql_generation", "status": "success", "metadata": {"candidate_sql": base["sql"]}},
            {"name": "sql_guard", "step_type": "sql_guard", "status": "success", "metadata": {}},
            {"name": "sql_execution", "step_type": "sql_query", "status": "success", "metadata": {}},
        ]
    base["trace_steps"] = steps
    return base


def _write_frozen_inputs(tmp_path: Path, cases: list[EvalCase]) -> tuple[Path, Path, Path]:
    """写一轮六类输入，模拟历史 run 的 trace/report/triage 三份只读证据。"""

    modes = ["normal", "timeout", "guard", "normal", "normal", "normal"]
    traces = [_trace(case, trace_id=f"trace-{index}", mode=mode) for index, (case, mode) in enumerate(zip(cases, modes), start=1)]
    trace_path = tmp_path / "traces.jsonl"
    trace_path.write_text("\n".join(json.dumps(item) for item in traces) + "\n", encoding="utf-8")
    report_path = tmp_path / "report.md"
    score_rows = []
    for case in cases:
        passed = "False" if case.case_id == "mismatch" else "True"
        name = "rule:manual_review" if case.check_type == "manual" else "rule:contains"
        reason = "manual_review_required" if case.check_type == "manual" else "fixture"
        score_rows.append(f"| {case.case_id} | {name} | 1.0 | {passed} | False | {reason} |")
    report_path.write_text(
        "# historical report\n\n## Score Summary\n\n| case_id | name | value | passed | skipped | reason |\n|---|---|---:|---|---|---|\n"
        + "\n".join(score_rows)
        + "\n\n## Next\n",
        encoding="utf-8",
    )
    triage_path = tmp_path / "triage.json"
    triage_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": case.case_id,
                        "trace_id": f"trace-{index}",
                        "failed": mode in {"timeout", "guard"},
                        "failure_stage": "query_plan" if mode == "timeout" else "sql_guard" if mode == "guard" else "unknown",
                        "primary_root_cause": "external_service" if mode == "timeout" else "code_issue" if mode == "guard" else "mixed_or_unknown",
                        "semantic_status": "not_observed" if mode == "timeout" else "not_applicable",
                        "needs_action": "manual_review" if case.check_type == "manual" else "fix_pipeline",
                    }
                    for index, (case, mode) in enumerate(zip(cases, modes), start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    return trace_path, report_path, triage_path


def test_build_audit_records_covers_six_fixture_shapes(tmp_path: Path) -> None:
    """正常 SQL、timeout、Guard 拦截、manual、结果错与缺 trace 都有明确、不静默的路径。"""

    cases = [
        _case("normal"),
        _case("timeout"),
        _case("guard"),
        _case("manual", check_type="manual", check={"type": "manual"}),
        _case("mismatch", check_type="equals", check={"type": "equals", "value": "expected"}),
        _case("missing"),
    ]
    trace_path, report_path, triage_path = _write_frozen_inputs(tmp_path, cases)
    manifest, records = build_audit_records(
        cases=cases,
        trace_path=trace_path,
        report_path=report_path,
        triage_path=triage_path,
        project_root=tmp_path,
        run_id="fixture-run",
        case_contract_version="fixture-v1",
        runtime_metadata={"oracle": "fixture"},
    )
    assert manifest.case_count == 6
    assert len(records) == 6
    assert records[0]["pipeline_evidence"]["candidate_sql"] == "SELECT product_name FROM products"
    assert records[1]["pipeline_evidence"]["sql_state"] == "unavailable"
    assert records[2]["pipeline_evidence"]["sql_state"] == "blocked"
    assert records[3]["automated_verdict"]["review_required_reconstructed"] is True
    assert records[4]["automated_verdict"]["runner_passed_reconstructed"] is False

    verdicts = {
        case.case_id: {"verdict": "unavailable" if case.case_id == "timeout" else "pass", "root_cause": "external_service" if case.case_id == "timeout" else "model_capability", "reason": "fixture evidence", "evidence": ["trace"], "confidence": "high"}
        for case in cases
    }
    reconciled = apply_audit_verdicts(records, verdicts)
    summary = summarize_reconciliation(reconciled)
    assert summary["raw_case_count"] == 6
    assert summary["review_pending_count"] == 1
    assert records[0]["result_evidence"]["automatic_score_evidence"].startswith("legacy_frozen_report")


def test_build_audit_records_rejects_missing_trace(tmp_path: Path) -> None:
    """缺 trace 是证据不足输入错误，不能通过默认值伪造一条审计记录。"""

    case = _case("only")
    trace_path, report_path, triage_path = _write_frozen_inputs(tmp_path, [case])
    payload = json.loads(triage_path.read_text(encoding="utf-8"))
    payload["cases"][0]["trace_id"] = "missing-trace"
    triage_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="audit trace missing"):
        build_audit_records(cases=[case], trace_path=trace_path, report_path=report_path, triage_path=triage_path, project_root=tmp_path, run_id="fixture", case_contract_version="v1", runtime_metadata={})
