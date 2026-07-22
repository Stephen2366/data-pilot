"""Phase 3A M8 eval 基线测试。

★ M8 的职责不是提升旧链路正确率，而是先把 10 条新库 regression 的输入、评分标签和
baseline 报告冻结下来。后续 M9-M12 才在这个基准上证明新 Text2SQL pipeline 的收益。
"""

from pathlib import Path

import yaml

from eval.run_eval import EvalCase, _score_case, load_cases, write_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE3A_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
SMOKE_CASES = PROJECT_ROOT / "eval" / "cases" / "smoke.yaml"


def test_phase3a_regression_cases_keep_m8_shape() -> None:
    """10 条 Phase 3A regression 必须保持计划要求的 2/3/3/2 比例和 M8 字段。"""

    payload = yaml.safe_load(PHASE3A_CASES.read_text(encoding="utf-8")) or {}
    cases = list(payload.get("cases") or [])
    task_types = [case["task_type"] for case in cases]

    assert len(cases) == 10
    assert task_types.count("simple_sql") == 2
    assert task_types.count("aggregation") == 3
    assert task_types.count("multi_table") == 3
    assert task_types.count("security") == 2

    for case in cases:
        assert isinstance(case.get("expected_tables"), list)
        assert isinstance(case.get("expected_columns"), list)
        assert isinstance(case.get("expected_metrics"), list)
        assert case["security_expectation"] in {"allow", "block"}


def test_load_cases_accepts_phase3a_fields_and_old_smoke_defaults() -> None:
    """M8 新字段要可读，但不能反向要求 M6 smoke 补字段。"""

    phase3a_cases = load_cases(PHASE3A_CASES)
    smoke_cases = load_cases(SMOKE_CASES)

    assert phase3a_cases[2].expected_metrics == ["gmv"]
    assert phase3a_cases[2].expected_trace_steps == []
    assert phase3a_cases[2].pipeline_mode == "baseline"

    assert smoke_cases[0].expected_metrics == []
    assert smoke_cases[0].expected_trace_steps == []
    assert smoke_cases[0].pipeline_mode == "baseline"


def test_challenge_suite_is_superset_of_formal_regression() -> None:
    """16 条 challenge 要作为 formal regression 的扩展集，避免两套题本各说各话。"""

    challenge_payload = yaml.safe_load(CHALLENGE_CASES.read_text(encoding="utf-8")) or {}
    raw_challenge_cases = list(challenge_payload.get("cases") or [])
    formal_cases = load_cases(PHASE3A_CASES)
    challenge_cases = load_cases(CHALLENGE_CASES)
    formal_questions = {case.question for case in formal_cases}
    challenge_questions = {case.question for case in challenge_cases}

    assert len(formal_questions) == 10
    assert len(challenge_questions) == 16
    assert formal_questions <= challenge_questions
    assert len(challenge_questions - formal_questions) == 6
    assert all("expected_metrics" in case for case in raw_challenge_cases)
    assert all(isinstance(case.expected_metrics, list) for case in challenge_cases)


def test_score_case_returns_minimal_issue_tags() -> None:
    """评分失败时返回稳定 issue tag，报告和后续对照不用再解析自然语言 reason。"""

    case = EvalCase(
        case_id="p3a_missing_column",
        task_type="aggregation",
        question="2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="baseline",
        security_expectation="allow",
        check_type="contains",
        check_value="gmv",
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["order_amount"],
    }

    score = _score_case(case, body, 200)

    assert score.passed is False
    assert score.issue_tags == ["missing_column"]


def test_manual_challenge_case_requires_review_without_hiding_success() -> None:
    """困难诊断题可先跑通结构，但报告必须提示人工复核。"""

    case = EvalCase(
        case_id="db_hard_manual",
        task_type="difficult_diagnosis",
        question="数码电子及其子类目 2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["product_categories", "products", "order_items", "orders"],
        expected_columns=["root_category", "gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="baseline",
        security_expectation="allow",
        check_type="manual",
        check_value="递归 CTE，Phase 3A 诊断素材",
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["product_categories", "products", "order_items", "orders"],
        "columns": ["root_category", "gmv"],
    }

    score = _score_case(case, body, 200)

    assert score.passed is True
    assert score.reason == "manual_review_required"
    assert score.review_required is True


def test_manual_challenge_failure_still_requires_review() -> None:
    """manual 困难题失败时也要显式标复核，避免被当成普通失败丢失诊断语义。"""

    case = EvalCase(
        case_id="db_hard_manual_missing",
        task_type="difficult_diagnosis",
        question="2026 年 6 月各商品平均售价是多少？",
        user_role="ops",
        expected_tables=["products", "product_price_history"],
        expected_columns=["product_name", "avg_price"],
        expected_metrics=["avg_selling_price"],
        expected_trace_steps=[],
        pipeline_mode="baseline",
        security_expectation="allow",
        check_type="manual",
        check_value="SCD 时间窗口 JOIN，Phase 3A 诊断素材",
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["products"],
        "columns": ["product_name"],
    }

    score = _score_case(case, body, 200)

    assert score.passed is False
    assert score.issue_tags == ["missing_table"]
    assert score.review_required is True


def test_report_includes_issue_tags_and_sql(tmp_path: Path) -> None:
    """baseline Markdown 要能人工回读 issue tag 和 SQL，而不只看 pass/fail。"""

    case = load_cases(PHASE3A_CASES)[0]
    report_path = tmp_path / "phase3a-baseline.md"
    score = _score_case(
        case,
        {
            "route": "sql",
            "safety_status": "passed",
            "tables_used": ["products"],
            "columns": ["product_name", "category", "status"],
            "sql": "SELECT product_name, category, status FROM products",
        },
        200,
    )
    from eval.run_eval import EvalResult

    write_report(
        [
            EvalResult(
                case=case,
                passed=score.passed,
                reason=score.reason,
                issue_tags=score.issue_tags,
                review_required=score.review_required,
                status_code=200,
                route="sql",
                safety_status="passed",
                error_type=None,
                trace_id="trace-m8",
                sql="SELECT product_name, category, status FROM products",
                response_body={},
            )
        ],
        report_path,
    )

    report = report_path.read_text(encoding="utf-8")
    assert "issue_tags" in report
    assert "review_required" in report
    assert "trace-m8" in report
    assert "SELECT product_name, category, status FROM products" in report
