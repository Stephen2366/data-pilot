"""Phase 3A M8 eval 基线测试。

★ M8 的职责不是提升旧链路正确率，而是先把 10 条新库 regression 的输入、评分标签和
baseline 报告冻结下来。后续 M9-M12 才在这个基准上证明新 Text2SQL pipeline 的收益。
"""

from pathlib import Path

import yaml

from eval.run_eval import EvalCase, EvalResult, _score_case, load_cases, write_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE3A_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml"
CHALLENGE_CASES = PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml"
DIAGNOSTIC_CASES = PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"
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


def test_challenge_cases_carry_diagnostic_capability_metadata() -> None:
    """M8.5 的 32 条 capability summary 需要继承 challenge 16 条的能力标签。"""

    cases = {case.case_id: case for case in load_cases(CHALLENGE_CASES)}

    assert cases["db_core_001"].phase3a_capabilities == [
        "schema_retrieval",
        "query_plan",
        "trace_steps",
    ]
    assert cases["db_hard_001"].phase3a_blocking is False
    assert "manual_review" in cases["db_hard_001"].case_properties
    assert cases["db_sec_001"].phase3a_capabilities == ["security_guard"]


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


def test_expected_value_check_fails_when_metric_value_is_null() -> None:
    """固定事实数值检查必须拦住 GMV=NULL，避免列名命中伪装成通过。"""

    case = EvalCase(
        case_id="p3a_gmv_null",
        task_type="aggregation",
        question="2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="expected_value",
        check_value="",
        check={"type": "expected_value", "field": "gmv", "value": 11285752.00, "tolerance": 0.01},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["gmv"],
        "rows": [{"gmv": None}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is False
    assert score.issue_tags == ["unexpected_error"]
    assert "expected_value" in score.reason


def test_expected_value_check_passes_when_metric_matches_within_tolerance() -> None:
    """固定事实数值在容差内时应通过，避免 scorer 只会报错不能确认修复效果。"""

    case = EvalCase(
        case_id="p3a_gmv_value",
        task_type="aggregation",
        question="2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="expected_value",
        check_value="",
        check={"type": "expected_value", "field": "gmv", "value": 11285752.00, "tolerance": 0.01},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["gmv"],
        "rows": [{"gmv": "11285752.00"}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.reason == "expected_value_ok"


def test_expected_columns_accept_configured_aliases() -> None:
    """列名评分允许 case 显式配置别名，避免把 usage_count 误判成 SQL 失败。"""

    case = EvalCase(
        case_id="p3a_coupon_alias",
        task_type="multi_table",
        question="JUNE_FIXED_50 在哪个渠道使用最多？",
        user_role="ops",
        expected_tables=["orders", "channels"],
        expected_columns=["channel_name", "coupon_order_count"],
        expected_metrics=["coupon_usage_rate"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="contains",
        check_value="Mobile App",
        expected_column_aliases={"coupon_order_count": ["usage_count"]},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders", "channels"],
        "columns": ["channel_name", "usage_count"],
        "rows": [{"channel_name": "Mobile App", "usage_count": 650}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.reason == "ok"


def test_expected_value_check_reads_configured_field_alias() -> None:
    """数值检查也要复用列别名，否则 total_net_revenue 这类正确值会先被挡住。"""

    case = EvalCase(
        case_id="p3a_net_revenue_alias",
        task_type="aggregation",
        question="2026 年 6 月净收入是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["net_revenue"],
        expected_metrics=["net_revenue"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="expected_value",
        check_value="",
        check={"type": "expected_value", "field": "net_revenue", "value": 11293058.25, "tolerance": 0.01},
        expected_column_aliases={"net_revenue": ["total_net_revenue"]},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["total_net_revenue"],
        "rows": [{"total_net_revenue": "11293058.25"}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.reason == "expected_value_ok"


def test_expected_value_check_accepts_single_metric_column_alias() -> None:
    """单指标固定事实题只有一列结果时，应以数值为准，避免中文别名被误判成缺列。"""

    case = EvalCase(
        case_id="p3a_gmv_localized_alias",
        task_type="aggregation",
        question="2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="expected_value",
        check_value="",
        check={"type": "expected_value", "field": "gmv", "value": 11285752.00, "tolerance": 0.01},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["2026年6月GMV"],
        "rows": [{"2026年6月GMV": "11285752.00"}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.reason == "expected_value_ok"


def test_result_match_case_fails_when_generated_rows_do_not_match_expected_sql() -> None:
    """result_match 要执行 expected_sql 对照，不能只因表列命中就放过错误结果。"""

    case = EvalCase(
        case_id="p3a_result_match_wrong_value",
        task_type="core_metric",
        question="2026 年 6 月 GMV 是多少？",
        user_role="ops",
        expected_tables=["orders"],
        expected_columns=["gmv"],
        expected_metrics=["gmv"],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="result_match",
        check_value="",
        expected_sql="SELECT 11285752.00 AS gmv",
        check={"type": "result_match", "tolerance": 0.01},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": ["orders"],
        "columns": ["gmv"],
        "rows": [{"gmv": "1.00"}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is False
    assert score.issue_tags == ["result_mismatch"]


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
    write_report(
        [
            EvalResult(
                case=case,
                passed=score.passed,
                reason=score.reason,
                issue_tags=score.issue_tags,
                review_required=score.review_required,
                skipped_due_to_pipeline_mode=score.skipped_due_to_pipeline_mode,
                status_code=200,
                route="sql",
                safety_status="passed",
                error_type=None,
                trace_id="trace-m8",
                sql="SELECT product_name, category, status FROM products",
                response_body={},
                actual_pipeline_mode=case.pipeline_mode,
            )
        ],
        report_path,
    )

    report = report_path.read_text(encoding="utf-8")
    assert "issue_tags" in report
    assert "review_required" in report
    assert "trace-m8" in report
    assert "SELECT product_name, category, status FROM products" in report


def test_diagnostic_extra_cases_keep_m8_5_shape() -> None:
    """M8.5 只维护新增 16 条 extra case，不能复制 challenge 16 条。"""

    payload = yaml.safe_load(DIAGNOSTIC_CASES.read_text(encoding="utf-8")) or {}
    cases = list(payload.get("cases") or [])
    ids = {case["id"] for case in cases}
    challenge_ids = {case.case_id for case in load_cases(CHALLENGE_CASES)}

    assert len(cases) == 16
    assert ids.isdisjoint(challenge_ids)
    assert {case["pipeline_mode"] for case in cases} == {"new_text2sql"}

    for case in cases:
        assert isinstance(case.get("phase3a_capabilities"), list)
        assert case["phase3a_capabilities"]
        assert isinstance(case.get("phase3a_blocking"), bool)
        assert isinstance(case.get("check"), dict)
        assert case["check"].get("type")


def test_load_cases_merges_extra_files_and_keeps_source_file() -> None:
    """runner 用 `--cases + --extra-cases` 拼成 32 条，并给每条保留来源文件。"""

    cases = load_cases(CHALLENGE_CASES, extra_cases=[DIAGNOSTIC_CASES])

    assert len(cases) == 32
    assert len({case.case_id for case in cases}) == 32
    assert cases[0].source_file == "eval/cases/database-upgrade-challenge.yaml"
    assert cases[-1].source_file == "eval/cases/phase3a-diagnostic-benchmark.yaml"
    assert any(case.case_id == "db_plan_001" for case in cases)


def test_diagnostic_linked_and_multi_answer_cases_are_explicit() -> None:
    """共享问题和多答案 case 要结构化标注，避免 M12 对照时口径漂移。"""

    cases = {case.case_id: case for case in load_cases(CHALLENGE_CASES, extra_cases=[DIAGNOSTIC_CASES])}

    linked = cases["db_plan_001"]
    source = cases["db_multi_003"]
    multi_answer = cases["db_schema_003"]

    assert linked.linked_case_id == "db_multi_003"
    assert linked.question == source.question
    assert "SUM(order_amount)" in str(linked.expected_plan)
    assert "SUM(o.order_amount)" in source.expected_sql

    assert multi_answer.expected_tables_alternatives
    assert multi_answer.check_type == "schema_context_match"
    assert multi_answer.check.get("match_mode") == "any_alternative"


def test_challenge_enables_minimal_result_match_for_core_sql_cases() -> None:
    """M14-lite 至少让 5 条核心 SQL case 走 expected_sql 结果对照。"""

    cases = load_cases(CHALLENGE_CASES)
    result_match_cases = [
        case
        for case in cases
        if case.check_type == "result_match" and "manual_review" not in case.case_properties
    ]

    assert len(result_match_cases) >= 5
    assert all(case.expected_sql.strip() for case in result_match_cases)


def test_diagnostic_out_of_scope_hybrid_attribution_is_non_blocking_manual_review() -> None:
    """知识库归因属于后续 Hybrid 语义层，不能作为 Phase 3A Text2SQL 硬门。"""

    cases = {case.case_id: case for case in load_cases(DIAGNOSTIC_CASES)}
    case = cases["db_plan_003"]

    assert case.phase3a_blocking is False
    assert "manual_review" in case.case_properties
    assert "hybrid_attribution" in case.case_properties


def test_baseline_skips_new_pipeline_only_checks_without_counting_failure() -> None:
    """旧链路 baseline 遇到 plan / trace / local schema 专属检查时要跳过，不伪装成失败。"""

    case = {case.case_id: case for case in load_cases(DIAGNOSTIC_CASES)}["db_plan_001"]

    score = _score_case(case, {}, 0, actual_pipeline_mode="baseline")

    assert score.passed is False
    assert score.skipped_due_to_pipeline_mode is True
    assert score.issue_tags == ["skipped_due_to_pipeline_mode"]
    assert score.reason == "skipped_due_to_pipeline_mode"


def test_diagnostic_report_includes_source_mode_and_capability_summary(tmp_path: Path) -> None:
    """M8.5 报告要能看出来源、实际 pipeline mode、skip 和 capability 覆盖。"""

    case = {case.case_id: case for case in load_cases(DIAGNOSTIC_CASES)}["db_plan_001"]
    report_path = tmp_path / "phase3a-diagnostic-baseline.md"
    score = _score_case(case, {}, 0, actual_pipeline_mode="baseline")

    write_report(
        [
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
                actual_pipeline_mode="baseline",
            )
        ],
        report_path,
    )

    report = report_path.read_text(encoding="utf-8")
    assert "skipped_due_to_pipeline_mode: 1" in report
    assert "## Capability Summary" in report
    assert "source_file" in report
    assert "configured_pipeline_mode" in report
    assert "actual_pipeline_mode" in report
    assert "phase3a-diagnostic-benchmark.yaml" in report
