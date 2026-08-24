"""M24 SQLPlanFidelityContract 深 module interface 回归测试。

测试只穿过 ``evaluate_sql_plan_fidelity`` 这个 seam，不依赖内部 helper。这样未来更换
sqlglot 归一化实现时，只要 interface 行为不变，测试无需跟着 implementation 重写。
"""

from __future__ import annotations

import pytest

from engine.nl2sql.fidelity_contract import evaluate_sql_plan_fidelity
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import load_domain_schema


def _step(**overrides: object) -> QueryPlanStep:
    """构造最小已验证计划；每个 case 只声明自己关心的合同。"""

    payload: dict[str, object] = {
        "step_id": "step_1",
        "step_index": 1,
        "purpose": "验证 SQL 保真",
        "tables": ["orders", "channels"],
        "output_columns": [],
    }
    payload.update(overrides)
    return QueryPlanStep(**payload)


@pytest.mark.parametrize(
    ("order_by", "limit", "sql"),
    [
        (["channels.channel_name ASC"], None, "SELECT c.channel_name FROM channels c ORDER BY c.channel_name ASC"),
        (
            ["SUM(orders.order_amount) DESC"],
            None,
            "SELECT SUM(o.order_amount) AS gmv FROM orders o ORDER BY `gmv` DESC",
        ),
        (
            ["SUM(orders_wide.actual_amount) DESC"],
            None,
            "SELECT channel_name, SUM(actual_amount) AS gmv FROM orders_wide "
            "GROUP BY channel_name ORDER BY SUM(actual_amount) DESC",
        ),
        (
            ["COUNT(DISTINCT order_coupons.order_id) DESC"],
            1,
            "SELECT c.channel_name, COUNT(DISTINCT oc.order_id) AS used_order_count "
            "FROM orders o JOIN order_coupons oc ON o.id=oc.order_id "
            "JOIN channels c ON c.id=o.channel_id GROUP BY c.channel_name "
            "ORDER BY used_order_count DESC LIMIT 1",
        ),
    ],
)
def test_contract_accepts_proven_semantic_equivalences(order_by: list[str], limit: int | None, sql: str) -> None:
    """只放行 M22/M23 trace 已证明的四类 SQL 等价形式。"""

    result = evaluate_sql_plan_fidelity(
        plan_step=_step(order_by=order_by, limit=limit),
        candidate_sql=sql,
        domain_schema=load_domain_schema(),
    )

    assert result.status == "passed"
    assert result.reason_code == "fidelity_ok"


def test_contract_accepts_only_exact_month_bucket_dialect_translation() -> None:
    """DATE_TRUNC→DATE_FORMAT 只在同字段、month、固定首日格式时登记窄等价。"""

    schema = load_domain_schema()
    step = _step(
        tables=["refunds"],
        order_by=["month ASC"],
        output_columns=["month"],
        output_expressions={"month": "DATE_TRUNC('month', refunds.processed_at)"},
    )
    accepted = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT DATE_FORMAT(refunds.processed_at, '%Y-%m-01') AS month "
            "FROM refunds GROUP BY DATE_FORMAT(refunds.processed_at, '%Y-%m-01') "
            "ORDER BY month ASC"
        ),
        domain_schema=schema,
    )

    assert accepted.status == "passed"
    assert accepted.narrow_equivalences == (
        "month_bucket_dialect_translation:date_trunc_to_date_format",
    )

    rejected_sql = (
        "SELECT {expression} AS month FROM refunds GROUP BY {expression} ORDER BY month {direction}"
    )
    rejected = (
        rejected_sql.format(
            expression="DATE_FORMAT(refunds.requested_at, '%Y-%m-01')",
            direction="ASC",
        ),
        rejected_sql.format(
            expression="DATE_FORMAT(refunds.processed_at, '%Y-%m')",
            direction="ASC",
        ),
        rejected_sql.format(
            expression="DATE_FORMAT(refunds.processed_at, '%Y-%m-01')",
            direction="DESC",
        ),
    )
    for sql in rejected:
        result = evaluate_sql_plan_fidelity(
            plan_step=step,
            candidate_sql=sql,
            domain_schema=schema,
        )
        assert result.status == "failed"


@pytest.mark.parametrize(
    ("step", "sql", "reason_code"),
    [
        (
            _step(order_by=["products.id ASC"], limit=10),
            "SELECT id FROM products ORDER BY id DESC LIMIT 10",
            "order_direction_mismatch",
        ),
        (
            _step(order_by=["products.product_name ASC"], limit=10),
            "SELECT product_name FROM products LIMIT 10",
            "missing_order_by",
        ),
        (
            _step(order_by=["orders.paid_at ASC"], limit=10),
            "SELECT paid_at FROM orders ORDER BY paid_at ASC",
            "limit_mismatch",
        ),
        (
            _step(
                order_by=["COUNT(orders.id) DESC", "channels.channel_name ASC"],
                tables=["orders", "channels"],
            ),
            "SELECT c.channel_name, COUNT(o.id) AS order_count FROM orders o "
            "JOIN channels c ON c.id=o.channel_id GROUP BY c.channel_name "
            "ORDER BY c.channel_name ASC, COUNT(o.id) DESC",
            "order_expression_or_sequence_mismatch",
        ),
    ],
)
def test_contract_rejects_true_order_or_limit_loss(
    step: QueryPlanStep,
    sql: str,
    reason_code: str,
) -> None:
    """方向、顺序、ORDER BY 和 LIMIT 的真实丢失不能因 AST 放宽而通过。"""

    result = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=sql,
        domain_schema=load_domain_schema(),
    )

    assert result.status == "failed"
    assert any(issue.code == reason_code for issue in result.issues)


@pytest.mark.parametrize(
    ("step", "sql", "reason_code"),
    [
        (
            _step(order_by=["orders.id ASC"], tables=["orders", "refunds"]),
            "SELECT o.id, r.id FROM orders o JOIN refunds r ON r.order_id=o.id ORDER BY id ASC",
            "ambiguous_order_expression",
        ),
        (
            _step(order_by=["orders.id ASC"]),
            "WITH x AS (SELECT id FROM orders) SELECT id FROM x ORDER BY id ASC",
            "ambiguous_order_expression",
        ),
        (
            _step(order_by=["products.product_name ASC"], tables=["products"]),
            "SELECT product_name FROM products ORDER BY 1 ASC",
            "ordinal_order_not_supported",
        ),
    ],
)
def test_contract_is_conservative_for_ambiguous_scope(
    step: QueryPlanStep,
    sql: str,
    reason_code: str,
) -> None:
    """歧义、跨 derived scope 与 ordinal order 都必须返回 indeterminate。"""

    result = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=sql,
        domain_schema=load_domain_schema(),
    )

    assert result.status == "indeterminate"
    assert result.reason_code == reason_code


def test_contract_does_not_let_candidate_sql_define_a_missing_plan_alias_binding() -> None:
    """缺少计划侧 alias 绑定时，候选 SQL 不能靠同名 SELECT alias 自证正确。"""

    result = evaluate_sql_plan_fidelity(
        plan_step=_step(order_by=["order_count DESC"], output_columns=["order_count"]),
        candidate_sql="SELECT SUM(order_amount) AS order_count FROM orders ORDER BY order_count DESC",
        domain_schema=load_domain_schema(),
    )

    assert result.status == "indeterminate"
    assert result.reason_code == "ambiguous_order_expression"


def test_contract_enforces_exact_projection_and_display_order() -> None:
    """自动链路采用 exact set + exact order；table qualifier 不属于最终展示列名。"""

    schema = load_domain_schema()
    step = _step(output_columns=["channels.channel_name", "order_count"])
    exact = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT c.channel_name, COUNT(o.id) AS order_count FROM channels c "
            "JOIN orders o ON o.channel_id=c.id GROUP BY c.channel_name"
        ),
        domain_schema=schema,
    )
    reordered = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT COUNT(o.id) AS order_count, c.channel_name FROM channels c "
            "JOIN orders o ON o.channel_id=c.id GROUP BY c.channel_name"
        ),
        domain_schema=schema,
    )
    extra = evaluate_sql_plan_fidelity(
        plan_step=step,
        candidate_sql=(
            "SELECT c.channel_name, c.channel_code, COUNT(o.id) AS order_count FROM channels c "
            "JOIN orders o ON o.channel_id=c.id GROUP BY c.channel_name, c.channel_code"
        ),
        domain_schema=schema,
    )

    assert exact.status == "passed"
    assert reordered.reason_code == "projection_order_mismatch"
    assert extra.reason_code == "projection_set_mismatch"


def test_contract_trace_evidence_is_complete_and_replayable() -> None:
    """trace 同时保存完整 SQL、结构化比较结果、hash 与 preview，preview 不再是唯一证据。"""

    sql = "SELECT product_name FROM products ORDER BY product_name ASC LIMIT 10"
    result = evaluate_sql_plan_fidelity(
        plan_step=_step(
            tables=["products"],
            order_by=["products.product_name ASC"],
            limit=10,
            output_columns=["products.product_name"],
        ),
        candidate_sql=sql,
        domain_schema=load_domain_schema(),
    )
    metadata = result.to_trace_metadata()

    assert metadata["candidate_sql"] == sql
    assert len(metadata["candidate_sql_hash"]) == 64
    assert metadata["comparison_rule"] == "sqlglot_ast_semantic_fidelity"
    assert metadata["contract_status"] == "passed"
    assert metadata["normalized_sql"]
    assert metadata["planned_output_bindings"] == {}
    assert metadata["observed_output_bindings"] == {}
