"""M25：可信分母、两轴归因、调用证据和能力反例的聚焦门禁。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from eval.run_eval import EvalCase, EvalResult, load_cases
from eval.scorers.base import EvalScoreDetail
from eval.triage import analyze_eval_run, triage_result
from engine.nl2sql.fidelity_contract import evaluate_sql_plan_fidelity
from engine.nl2sql.llm_call import LLMGenerationError, execute_llm_call
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import load_domain_schema


def _case(**overrides: object) -> EvalCase:
    payload: dict[str, object] = {
        "case_id": "case_1",
        "task_type": "aggregation",
        "question": "测试问题",
        "user_role": "ops",
        "expected_tables": [],
        "expected_columns": [],
        "expected_metrics": [],
        "expected_trace_steps": [],
        "pipeline_mode": "new_text2sql",
        "security_expectation": "allow",
        "check_type": "result_match",
        "check_value": "",
        "semantic_group_id": "group_1",
    }
    payload.update(overrides)
    return EvalCase(**payload)


def _result(
    *,
    case: EvalCase | None = None,
    passed: bool,
    details: list[EvalScoreDetail],
    error_type: str | None = None,
    review_required: bool = False,
) -> EvalResult:
    return EvalResult(
        case=case or _case(),
        passed=passed,
        reason="ok" if passed else "failed",
        issue_tags=[],
        review_required=review_required,
        skipped_due_to_pipeline_mode=False,
        status_code=200,
        route="sql",
        safety_status="allowed",
        error_type=error_type,
        trace_id="trace-1",
        sql="SELECT 1" if passed else None,
        response_body={},
        actual_pipeline_mode="new_text2sql",
        score_details=details,
    )


def test_diagnostic_denominator_is_32_raw_but_26_independent_groups() -> None:
    cases = load_cases(
        Path("eval/cases/database-upgrade-challenge.yaml"),
        extra_cases=[Path("eval/cases/phase3a-diagnostic-benchmark.yaml")],
    )

    assert len(cases) == 32
    assert len({case.semantic_group_id for case in cases}) == 26


def test_rewritten_case_contracts_state_hidden_constraints() -> None:
    cases = {case.case_id: case for case in load_cases(Path("eval/cases/database-upgrade-challenge.yaml"))}

    assert "按商品名称升序" in cases["db_simple_001"].question
    assert "仅返回订单号、订单金额和支付时间" in cases["db_simple_002"].question
    assert "2026 年 6 月" in cases["db_multi_002"].question
    assert "算术平均" in cases["db_hard_003"].question
    assert "refund_status = 'completed'" in cases["db_core_002"].expected_sql
    assert "COUNT(DISTINCT r.order_id)" in cases["db_core_002"].expected_sql


def test_refund_rate_counterexample_rejects_record_count_and_non_completed_refunds() -> None:
    """一单多退款记录 + rejected 记录会让旧分子虚高，反例固定新业务口径。"""

    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE eligible_orders (order_id INTEGER PRIMARY KEY);
        CREATE TABLE refunds (id INTEGER PRIMARY KEY, order_id INTEGER, refund_status TEXT);
        INSERT INTO eligible_orders VALUES (1), (2), (3);
        INSERT INTO refunds VALUES
          (1, 1, 'completed'),
          (2, 1, 'completed'),
          (3, 2, 'rejected');
        """
    )
    completed_order_rate = db.execute(
        "SELECT COUNT(DISTINCT CASE WHEN refund_status='completed' THEN order_id END) * 1.0 / "
        "(SELECT COUNT(*) FROM eligible_orders) FROM refunds"
    ).fetchone()[0]
    old_record_rate = db.execute(
        "SELECT COUNT(id) * 1.0 / (SELECT COUNT(*) FROM eligible_orders) FROM refunds"
    ).fetchone()[0]

    assert completed_order_rate == 1 / 3
    assert old_record_rate == 1.0


def test_refund_product_attribution_keeps_whole_order_fallback() -> None:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER);
        CREATE TABLE refunds (
          id INTEGER PRIMARY KEY, order_id INTEGER, order_item_id INTEGER, product_id INTEGER, refund_status TEXT
        );
        INSERT INTO order_items VALUES (11, 1, 10);
        INSERT INTO refunds VALUES (21, 1, NULL, 10, 'completed');
        """
    )
    correct = db.execute(
        "SELECT COUNT(DISTINCT r.order_id) FROM refunds r "
        "LEFT JOIN order_items oi ON oi.id=r.order_item_id "
        "WHERE r.refund_status='completed' AND COALESCE(oi.product_id,r.product_id)=10"
    ).fetchone()[0]
    wrong_inner_join = db.execute(
        "SELECT COUNT(DISTINCT r.order_id) FROM refunds r "
        "JOIN order_items oi ON oi.id=r.order_item_id "
        "WHERE r.refund_status='completed' AND oi.product_id=10"
    ).fetchone()[0]

    assert correct == 1
    assert wrong_inner_join == 0


class _TransientThenSuccessClient:
    provider_label = "FakeProvider"
    model = "fake-model"
    timeout = 12.0
    max_retries = 1
    retry_backoff_seconds = 0.0

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            raise LLMGenerationError("timed out", error_subtype="timeout", retryable=True)
        return "{}"


def test_llm_executor_records_transient_retry_attempts() -> None:
    client = _TransientThenSuccessClient()
    result = execute_llm_call(client, prompt="hello", system_prompt="system", stage="query_plan")

    assert client.calls == 2
    assert result.evidence.configured_timeout_seconds == 12.0
    assert [attempt.outcome for attempt in result.evidence.attempts] == ["error", "success"]
    assert result.evidence.attempts[0].error_subtype == "timeout"


def test_llm_executor_does_not_retry_non_transient_error() -> None:
    class BadRequestClient(_TransientThenSuccessClient):
        max_retries = 3

        def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
            self.calls += 1
            raise LLMGenerationError("bad request", error_subtype="http_400", retryable=False)

    client = BadRequestClient()
    try:
        execute_llm_call(client, prompt="hello", system_prompt="system", stage="sql_generation")
    except LLMGenerationError as exc:
        assert exc.call_evidence is not None
        assert len(exc.call_evidence.attempts) == 1
    else:
        raise AssertionError("non-transient error should propagate")
    assert client.calls == 1


def test_timeout_is_external_and_semantic_answer_is_not_observed() -> None:
    details = [EvalScoreDetail(name="rule:sql_success", value=0, passed=False, reason="LLM failed")]
    result = _result(passed=False, details=details, error_type="llm_generation_error")
    trace = {
        "trace_steps": [
            {
                "name": "query_plan",
                "step_type": "query_plan",
                "status": "error",
                "error_type": "llm_generation_error",
                "metadata": {
                    "error_subtype": "timeout",
                    "llm_call": {"attempts": [{"error_subtype": "timeout"}]},
                },
            }
        ]
    }

    triage = triage_result(result, trace)

    assert triage.failure_stage == "query_plan"
    assert triage.primary_root_cause == "external_service"
    assert triage.semantic_status == "not_observed"
    assert triage.error_subtype == "timeout"
    assert len(triage.evidence_chain) == 2


def test_root_cause_categories_follow_evidence_not_case_id() -> None:
    base = _result(passed=False, details=[EvalScoreDetail(name="rule:sql_success", value=0, passed=False)])
    retrieval = triage_result(
        base,
        {"trace_steps": [{"name": "schema_retrieval", "status": "blocked", "error_type": "insufficient_schema_context"}]},
    )
    code = triage_result(
        _result(passed=False, details=[], error_type="sql_execution_error"),
        {},
    )
    eval_contract = triage_result(
        _result(
            passed=False,
            details=[EvalScoreDetail(name="custom:broken_scorer", value=0, passed=False, reason="rubric mismatch")],
            review_required=True,
        ),
        {},
    )
    unknown = triage_result(_result(passed=False, details=[]), {})
    model = triage_result(
        _result(
            passed=False,
            details=[EvalScoreDetail(name="rule:result_match", value=0, passed=False, reason="wrong result")],
        ),
        {},
    )

    assert retrieval.primary_root_cause == "retrieval_issue"
    assert code.primary_root_cause == "code_issue"
    assert eval_contract.primary_root_cause == "eval_contract"
    assert unknown.primary_root_cause == "mixed_or_unknown"
    assert model.primary_root_cause == "model_capability"
    assert model.semantic_status == "observed_wrong"


def test_evidence_views_separate_raw_cases_groups_and_unavailable() -> None:
    correct = _result(
        case=_case(case_id="a", semantic_group_id="same"),
        passed=True,
        details=[EvalScoreDetail(name="rule:result_match", value=1, passed=True)],
    )
    timeout = _result(
        case=_case(case_id="b", semantic_group_id="same"),
        passed=False,
        details=[EvalScoreDetail(name="rule:sql_success", value=0, passed=False)],
        error_type="llm_generation_error",
    )
    triages = [
        triage_result(correct, {}),
        triage_result(
            timeout,
            {"trace_steps": [{"name": "query_plan", "status": "error", "error_type": "llm_generation_error", "metadata": {"error_subtype": "timeout"}}]},
        ),
    ]

    analysis = analyze_eval_run([correct, timeout], triages)

    assert analysis.raw_case_count == 2
    assert analysis.independent_group_count == 1
    assert analysis.views["end_to_end"].eligible_group_count == 1
    assert analysis.views["provider_reliability"].unavailable_case_count == 1


def test_recursive_category_sql_remains_indeterminate_without_scope_expansion() -> None:
    step = QueryPlanStep(
        step_id="step_1",
        step_index=1,
        purpose="递归一级类目销售额",
        tables=["product_categories", "products", "order_items", "orders"],
        output_columns=["root_category", "item_gmv"],
        order_by=["item_gmv DESC", "root_category ASC"],
    )
    sql = (
        "WITH RECURSIVE ct AS (SELECT id, category_name AS root_category FROM product_categories WHERE parent_id IS NULL "
        "UNION ALL SELECT c.id, ct.root_category FROM product_categories c JOIN ct ON c.parent_id=ct.id) "
        "SELECT ct.root_category, SUM(oi.line_amount) AS item_gmv FROM ct JOIN products p ON p.category_id=ct.id "
        "JOIN order_items oi ON oi.product_id=p.id JOIN orders o ON o.id=oi.order_id "
        "GROUP BY ct.root_category ORDER BY item_gmv DESC, ct.root_category ASC"
    )

    result = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=sql,
        domain_schema=load_domain_schema(),
    )

    assert result.status == "indeterminate"
    assert result.reason_code in {"ambiguous_order_expression", "unsupported_nested_scope"}


def test_recursive_category_counterexample_distinguishes_descendants_and_item_grain() -> None:
    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE categories (id INTEGER PRIMARY KEY, parent_id INTEGER, name TEXT);
        CREATE TABLE products (id INTEGER PRIMARY KEY, category_id INTEGER);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, order_amount REAL);
        CREATE TABLE order_items (order_id INTEGER, product_id INTEGER, line_amount REAL);
        INSERT INTO categories VALUES (1, NULL, '数码电子'), (2, 1, '耳机');
        INSERT INTO products VALUES (10, 1), (11, 2);
        INSERT INTO orders VALUES (100, 100.0);
        INSERT INTO order_items VALUES (100, 10, 20.0), (100, 11, 50.0);
        """
    )
    correct = db.execute(
        "WITH RECURSIVE ct(id) AS (SELECT id FROM categories WHERE id=1 "
        "UNION ALL SELECT c.id FROM categories c JOIN ct ON c.parent_id=ct.id) "
        "SELECT SUM(oi.line_amount) FROM ct JOIN products p ON p.category_id=ct.id "
        "JOIN order_items oi ON oi.product_id=p.id"
    ).fetchone()[0]
    wrong_missing_descendants = db.execute(
        "SELECT SUM(oi.line_amount) FROM categories c JOIN products p ON p.category_id=c.id "
        "JOIN order_items oi ON oi.product_id=p.id WHERE c.id=1"
    ).fetchone()[0]
    wrong_order_grain = db.execute(
        "WITH RECURSIVE ct(id) AS (SELECT id FROM categories WHERE id=1 "
        "UNION ALL SELECT c.id FROM categories c JOIN ct ON c.parent_id=ct.id) "
        "SELECT SUM(o.order_amount) FROM ct JOIN products p ON p.category_id=ct.id "
        "JOIN order_items oi ON oi.product_id=p.id JOIN orders o ON o.id=oi.order_id"
    ).fetchone()[0]

    assert correct == 70.0
    assert wrong_missing_descendants == 20.0
    assert wrong_order_grain == 200.0
