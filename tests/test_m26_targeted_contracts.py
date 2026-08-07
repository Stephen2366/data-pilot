"""M26 P2 定点回归：只覆盖审计已经确认的安全、保真、Context 和状态边界。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from eval.run_eval import EvalCase, EvalResult, load_cases
from eval.scorers.base import EvalScoreDetail
from eval.scorers.rule_scorers import score_case_rules
from eval.triage import triage_result, triage_summary
from engine.nl2sql.fidelity_contract import evaluate_sql_plan_fidelity
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import load_domain_schema
from engine.sql_guard.policy import extract_sql_access, validate_sql_policy


def _step(**overrides: object) -> QueryPlanStep:
    """构造 fidelity 计划，只让测试聚焦 `* 1.0` 的窄等价。"""

    payload: dict[str, object] = {
        "step_id": "step_1",
        "step_index": 1,
        "purpose": "设备转化率",
        "tables": ["user_behavior_log"],
        "output_columns": [],
    }
    payload.update(overrides)
    return QueryPlanStep(**payload)


def _eval_result(*, passed: bool, review_required: bool, error_type: str | None = None) -> EvalResult:
    """构造 triage 状态 fixture，不经过 HTTP 或 LLM。"""

    case = EvalCase(
        case_id="m26-status",
        task_type="test",
        question="状态测试",
        user_role="ops",
        expected_tables=[],
        expected_columns=[],
        expected_metrics=[],
        expected_trace_steps=[],
        pipeline_mode="new_text2sql",
        security_expectation="allow",
        check_type="manual" if review_required else "contains",
        check_value="",
    )
    return EvalResult(
        case=case,
        passed=passed,
        reason="fixture",
        issue_tags=[],
        review_required=review_required,
        skipped_due_to_pipeline_mode=False,
        status_code=200,
        route="sql",
        safety_status="passed",
        error_type=error_type,
        trace_id="trace-m26",
        sql=None,
        response_body={},
        actual_pipeline_mode="new_text2sql",
        score_details=[EvalScoreDetail(name="rule:manual_review", value=1, passed=True, review_required=True)]
        if review_required
        else [],
    )


def test_cte_name_is_not_an_rbac_table_but_internal_tables_remain_checked() -> None:
    """合法递归 CTE 不再误拦；越权物理表和敏感字段不能藏进 CTE。"""

    schema = load_domain_schema()
    recursive = """
    WITH RECURSIVE category_tree AS (
      SELECT id, parent_id FROM product_categories WHERE parent_id IS NULL
      UNION ALL
      SELECT child.id, child.parent_id
      FROM product_categories child JOIN category_tree tree ON child.parent_id = tree.id
    )
    SELECT id FROM category_tree
    """
    access = extract_sql_access(recursive, schema)
    assert access.tables == {"product_categories"}
    assert validate_sql_policy(recursive, user_role="ops", domain_schema=schema).is_allowed is True

    nested_forbidden = "WITH customer_orders AS (SELECT order_no FROM orders) SELECT order_no FROM customer_orders"
    forbidden = validate_sql_policy(nested_forbidden, user_role="customer_service", domain_schema=schema)
    assert forbidden.is_allowed is False
    assert "orders" in (forbidden.blocked_reason or "")

    sensitive_cte = "WITH user_contacts AS (SELECT id, email FROM users) SELECT email FROM user_contacts"
    sensitive = validate_sql_policy(sensitive_cte, user_role="ops", domain_schema=schema)
    assert sensitive.is_allowed is False
    assert "敏感字段" in (sensitive.blocked_reason or "")

    shadowing = "WITH orders AS (SELECT product_name FROM products) SELECT product_name FROM orders"
    shadow_access = extract_sql_access(shadowing, schema)
    assert shadow_access.tables == {"products"}
    assert validate_sql_policy(shadowing, user_role="demo_user", domain_schema=schema).is_allowed is True


def test_fidelity_accepts_only_documented_ratio_numeric_type_promotion() -> None:
    """`* 1.0` 可关闭已知假阴性，但改变分子或去掉 NULLIF 仍不能通过。"""

    schema = load_domain_schema()
    step = _step(order_by=["SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) DESC"])
    accepted = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT device_type FROM user_behavior_log GROUP BY device_type ORDER BY "
            "SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 / "
            "NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) DESC"
        ),
        domain_schema=schema,
    )
    changed_numerator = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT device_type FROM user_behavior_log GROUP BY device_type ORDER BY "
            "(SUM(CASE WHEN event_type = 'payment_success' THEN 1 ELSE 0 END) * 1.0 + 1) / "
            "NULLIF(SUM(CASE WHEN event_type = 'add_to_cart' THEN 1 ELSE 0 END), 0) DESC"
        ),
        domain_schema=schema,
    )
    assert accepted.status == "passed"
    assert accepted.narrow_equivalences == ("ratio_numeric_type_promotion:*1.0",)
    assert changed_numerator.status == "failed"


def test_schema_context_alternatives_score_the_schema_graph_not_output_columns() -> None:
    """`db_schema_003` 的 any-of alternatives 必须只由同请求 SchemaGraph 判定。"""

    case = next(
        case
        for case in load_cases(Path("eval/cases/phase3a-diagnostic-benchmark.yaml"))
        if case.case_id == "db_schema_003"
    )
    passing_body = {
        "route": "sql",
        "safety_status": "passed",
        "error_type": None,
        # 故意不给最终 columns：若仍走旧 column_recall，这条会失败。
        "columns": [],
        "_trace_steps": [
            {
                "step_type": "schema_context",
                "metadata": {
                    "tables": ["channels", "orders"],
                    "fields": ["channels.channel_name", "orders.order_amount", "orders.paid_at", "orders.channel_id"],
                    "metrics": [],
                },
            }
        ],
    }
    failing_body = {
        **passing_body,
        "_trace_steps": [
            {
                "step_type": "schema_context",
                "metadata": {"tables": ["orders_wide"], "fields": ["orders_wide.channel_name", "orders_wide.snapshot_at"], "metrics": []},
            }
        ],
    }
    passed_details = score_case_rules(case=case, body=passing_body, status_code=200, actual_pipeline_mode="new_text2sql")
    failed_details = score_case_rules(case=case, body=failing_body, status_code=200, actual_pipeline_mode="new_text2sql")
    assert [detail.name for detail in passed_details] == ["rule:safety_compliance", "rule:schema_context", "rule:sql_success"]
    assert passed_details[1].passed is True
    assert failed_details[1].passed is False
    assert "schema_context_alternatives_no_match" in failed_details[1].reason


def test_triage_separates_execution_failure_review_pending_and_external_unavailable() -> None:
    """兼容 failed 后仍可独立统计三类队列，避免 manual_review 混入执行失败。"""

    pending = triage_result(_eval_result(passed=True, review_required=True), {})
    timeout = triage_result(
        _eval_result(passed=False, review_required=False, error_type="llm_generation_error"),
        {"trace_steps": [{"name": "query_plan", "step_type": "query_plan", "status": "error", "error_type": "llm_generation_error", "metadata": {"llm_call": {"attempts": [{"error_subtype": "timeout"}]}}}]},
    )
    assert pending.failed is True and pending.execution_failed is False and pending.review_pending is True
    assert timeout.execution_failed is True and timeout.review_pending is False
    summary = triage_summary([pending, timeout])
    assert summary["execution_failed"] == 1
    assert summary["review_pending"] == 1
    assert summary["external_unavailable"] == 1


def test_refund_rate_counterfactual_exposes_missing_whole_order_fallback() -> None:
    """最小 SQLite fixture 让整单退款只归属 `refunds.product_id`，不能再被 Top1 偶然掩盖。"""

    db = sqlite3.connect(":memory:")
    db.executescript(
        """
        CREATE TABLE products (id INTEGER PRIMARY KEY, product_name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, paid_at TEXT, order_status TEXT);
        CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER);
        CREATE TABLE refunds (id INTEGER PRIMARY KEY, order_id INTEGER, order_item_id INTEGER, product_id INTEGER, refund_status TEXT);
        INSERT INTO products VALUES (1, 'Alpha'), (2, 'Beta');
        INSERT INTO orders VALUES (1, '2026-06-02', 'paid'), (2, '2026-06-03', 'paid');
        INSERT INTO order_items VALUES (10, 1, 1), (20, 2, 2);
        INSERT INTO refunds VALUES (100, 2, NULL, 2, 'completed');
        """
    )
    correct = db.execute(
        """
        WITH eligible AS (SELECT order_id, product_id FROM order_items),
        refunded AS (
          SELECT COALESCE(oi.product_id, r.product_id) AS product_id, COUNT(DISTINCT r.order_id) AS count_refund
          FROM refunds r LEFT JOIN order_items oi ON oi.id = r.order_item_id
          WHERE r.refund_status = 'completed' GROUP BY COALESCE(oi.product_id, r.product_id)
        )
        SELECT p.product_name, COALESCE(refunded.count_refund, 0) * 1.0 / COUNT(DISTINCT eligible.order_id) AS refund_rate
        FROM products p JOIN eligible ON eligible.product_id = p.id LEFT JOIN refunded ON refunded.product_id = p.id
        GROUP BY p.id, p.product_name, refunded.count_refund ORDER BY refund_rate DESC, p.product_name ASC LIMIT 1
        """
    ).fetchone()
    missing_fallback = db.execute(
        """
        SELECT p.product_name, COUNT(DISTINCT CASE WHEN r.refund_status = 'completed' THEN o.id END) * 1.0 / COUNT(DISTINCT o.id) AS refund_rate
        FROM products p JOIN order_items oi ON oi.product_id = p.id JOIN orders o ON o.id = oi.order_id
        LEFT JOIN refunds r ON r.order_item_id = oi.id GROUP BY p.id, p.product_name
        ORDER BY refund_rate DESC, p.product_name ASC LIMIT 1
        """
    ).fetchone()
    assert correct == ("Beta", 1.0)
    assert missing_fallback == ("Alpha", 0.0)
