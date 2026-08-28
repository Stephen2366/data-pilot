"""M50 用户实测修正：comparison QueryPlan 的窄边界回归。"""

from engine.nl2sql.planner import QueryPlan, QueryPlanStep, normalize_base_aggregate_plan


def test_comparison_base_aggregate_normalization_removes_upper_layer_outputs():
    """Agent comparison 只把月度基础金额交给 SQL，diff/rate 留给既有 completion。"""

    plan = QueryPlan(steps=[QueryPlanStep(
        step_id="step_1", step_index=1, purpose="比较两个月退款", tables=["refunds"],
        columns=["refunds.processed_at", "refunds.refund_amount"], metrics=["net_refund_amount"],
        aggregations=["SUM(refunds.refund_amount)", "nested diff expression", "rate expression"],
        group_by=["refunds.processed_at"], order_by=["month ASC", "diff DESC"],
        output_columns=["month", "net_refund_amount", "diff", "change_rate"],
        output_expressions={
            "month": "DATE_FORMAT(refunds.processed_at, '%Y-%m')",
            "net_refund_amount": "SUM(refunds.refund_amount)",
            "diff": "nested diff expression", "change_rate": "rate expression",
        },
    )])
    normalized, changed = normalize_base_aggregate_plan(plan)
    step = normalized.steps[0]
    assert changed is True
    assert step.output_columns == ["month", "net_refund_amount"]
    assert step.output_expressions == {
        "month": "DATE_FORMAT(refunds.processed_at, '%Y-%m')",
        "net_refund_amount": "SUM(refunds.refund_amount)",
    }
    assert step.aggregations == ["SUM(refunds.refund_amount)"]
    assert step.order_by == ["month ASC"]
    # 原计划不可变，便于 Trace/测试区分 provider 输出和受控规范化结果。
    assert plan.steps[0].output_columns[-2:] == ["diff", "change_rate"]
