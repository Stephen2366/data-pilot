"""M22 Eval Contract / QueryPlan → SQL 回归测试。

这些测试不调用真实 LLM：它们固定评测契约、结构化拒绝与 prompt 约束，避免一次模型波动
重新把 Context Contract、Output Contract 和语义拒绝混在一起。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from engine.nl2sql.pipeline import run_text2sql_pipeline
from eval.run_eval import EvalCase, EvalResult, _score_case, write_report
from engine.nl2sql.generator import SQLPlanContractError, validate_sql_plan_contract
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.prompt import build_local_schema_sql_prompt, build_query_plan_prompt
from engine.nl2sql.schema_loader import load_domain_schema
from engine.nl2sql.semantic_validation import validate_request_semantics
from engine.schema_retrieval.objects import SchemaGraph
from scripts.seed_data import seed_database


def _case(*, check_type: str, **overrides: object) -> EvalCase:
    """构造最小 M22 case；每个测试只覆盖自己的 contract 差异。"""

    payload = {
        "case_id": "m22_case",
        "task_type": "diagnostic",
        "question": "测试问题",
        "user_role": "ops",
        "expected_tables": ["orders"],
        "expected_columns": ["gmv"],
        "expected_metrics": ["gmv"],
        "expected_trace_steps": [],
        "pipeline_mode": "new_text2sql",
        "security_expectation": "allow",
        "check_type": check_type,
        "check_value": "",
    }
    payload.update(overrides)
    return EvalCase(**payload)


def test_schema_context_contract_reads_trace_metadata_not_final_output_columns() -> None:
    """局部 Schema 有内部字段、最终 SELECT 不返回它们时，Context Contract 仍应通过。"""

    case = _case(
        check_type="schema_context_size",
        expected_schema_context={
            "must_include_tables": ["orders", "order_items"],
            "must_include_columns": ["paid_at", "line_amount"],
        },
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "columns": ["product_name", "item_gmv"],
        "_trace_steps": [
            {
                "step_type": "schema_context",
                "metadata": {
                    "tables": ["orders", "order_items", "products"],
                    "fields": ["orders.paid_at", "order_items.line_amount", "products.product_name"],
                },
            }
        ],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.issue_tags == []


def test_plan_validation_contract_scores_structured_semantic_block_before_output_columns() -> None:
    """未知 supplier_name 被结构化拒绝时，不能先被空输出列误判为普通 column failure。"""

    case = _case(
        check_type="plan_validation_blocked",
        expected_columns=["supplier_name"],
        expected_issue_tag="missing_column",
        check={"type": "plan_validation_blocked", "expected_issue_tag": "missing_column"},
    )
    body = {
        "route": "sql",
        "safety_status": "blocked",
        "error_type": "plan_validation_failed",
        "columns": [],
        "_trace_steps": [
            {
                "step_type": "plan_validation",
                "metadata": {"issue_tags": ["missing_column"], "blocked_via": "semantic_request_validation"},
            }
        ],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.issue_tags == []


def test_result_match_accepts_case_declared_equivalent_alias() -> None:
    """coupon_order_count 的等价 alias 要同时通过列契约和 result_match。"""

    case = _case(
        check_type="result_match",
        expected_tables=[],
        expected_columns=["coupon_order_count"],
        expected_column_aliases={"coupon_order_count": ["used_order_count"]},
        expected_sql="SELECT 3 AS coupon_order_count",
        check={"type": "result_match", "tolerance": 0.01},
    )
    body = {
        "route": "sql",
        "safety_status": "passed",
        "tables_used": [],
        "columns": ["used_order_count"],
        "rows": [{"used_order_count": 3}],
    }

    score = _score_case(case, body, 200, actual_pipeline_mode="new_text2sql")

    assert score.passed is True
    assert score.reason == "result_match_ok"


def test_semantic_validation_distinguishes_known_unsupported_requests() -> None:
    """M22 只拒绝已证实无 Schema / 单步能力支撑的请求，不把问题伪装成 LLM 异常。"""

    schema = load_domain_schema()

    supplier = validate_request_semantics("查询商品的供应商名称", domain_schema=schema)
    hybrid = validate_request_semantics("统计每篇知识库文档带来的订单金额", domain_schema=schema)
    multi_step = validate_request_semantics("先查 6 月 GMV，再查退款率，最后对比", domain_schema=schema)

    assert supplier and supplier.issue_tag == "missing_column"
    assert hybrid and hybrid.issue_tag == "unsupported_relation"
    assert multi_step and multi_step.issue_tag == "unsupported_multi_step_plan"


@pytest.mark.parametrize(
    ("question", "expected_issue_tag"),
    [
        ("查询商品的供应商名称", "missing_column"),
        ("统计每篇知识库文档带来的订单金额", "unsupported_relation"),
        ("先查 6 月 GMV，再查退款率，最后对比", "unsupported_multi_step_plan"),
    ],
)
def test_pipeline_records_semantic_rejection_as_plan_validation(
    question: str, expected_issue_tag: str
) -> None:
    """三类不支持需求必须在 trace 留下语义拒绝，而不是等 LLM 调用失败后才停止。"""

    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            seed_database(session, reset_existing=True)
            result = run_text2sql_pipeline(question=question, user_role="ops", db=session, trace_id="m22-semantic")
        validation_step = next(step for step in result.trace_steps if step.step_type == "plan_validation")

        assert result.safety_status == "blocked"
        assert result.error_type == "plan_validation_failed"
        assert result.issue_tags == [expected_issue_tag]
        assert validation_step.metadata["blocked_via"] == "semantic_request_validation"
    finally:
        Base.metadata.drop_all(engine)


def test_avg_selling_price_prompt_requires_window_overlap() -> None:
    """SCD 历史售价不能只按 valid_from 落点过滤，SQL prompt 必须给 overlap 约束。"""

    graph = SchemaGraph(
        tables=["products", "product_price_history"],
        fields={
            "products": ["id", "product_name"],
            "product_price_history": ["product_id", "price", "valid_from", "valid_to"],
        },
        metrics=["avg_selling_price"],
        relations=[],
        join_paths=[],
    )
    step = QueryPlanStep(
        step_id="step_1", step_index=1, purpose="统计 6 月历史平均售价", tables=graph.tables,
        columns=["products.product_name", "product_price_history.price"], metrics=["avg_selling_price"],
    )

    prompt = build_local_schema_sql_prompt(
        question="2026 年 6 月各商品平均售价是多少？", user_role="ops", plan_step=step,
        schema_graph=graph, metrics=load_domain_schema().metrics,
    )

    assert "valid_from < 窗口结束" in prompt
    assert "valid_to IS NULL OR valid_to > 窗口开始" in prompt


def test_sql_plan_contract_preserves_order_by_and_rejects_silent_drop() -> None:
    """db_core_004 类排序一旦已进入 QueryPlan，就不能在 SQL generation 阶段丢失。"""

    step = QueryPlanStep(
        step_id="step_1", step_index=1, purpose="按渠道统计订单量", order_by=["order_count DESC"],
    )

    validate_sql_plan_contract(
        "SELECT channel_name, COUNT(*) AS order_count FROM orders GROUP BY channel_name ORDER BY order_count DESC",
        plan_step=step,
    )
    with pytest.raises(SQLPlanContractError, match="ORDER BY"):
        validate_sql_plan_contract(
            "SELECT channel_name, COUNT(*) AS order_count FROM orders GROUP BY channel_name",
            plan_step=step,
        )


def test_channel_order_count_plan_prompt_requires_stable_sort() -> None:
    """db_core_004 的排序必须先进入 QueryPlan，SQL contract 才能阻止后续生成阶段丢失它。"""

    graph = SchemaGraph(
        tables=["channels", "orders"],
        fields={"channels": ["id", "channel_name"], "orders": ["id", "channel_id"]},
        metrics=["order_count"], relations=[], join_paths=[],
    )

    prompt = build_query_plan_prompt(
        question="各渠道订单量是多少？", schema_graph=graph, metrics=load_domain_schema().metrics,
    )

    assert "order_count DESC, channels.channel_name ASC" in prompt


def test_report_separates_automated_manual_and_contract_adjustment_views(tmp_path: Path) -> None:
    """M22 报告必须把能力分、人工审查和因 case/scorer 修正的重分类显式分开。"""

    automated = _case(check_type="contains")
    manual = _case(check_type="manual", case_id="m22_manual", case_properties=["manual_review"])
    adjusted = _case(check_type="contains", case_id="m22_adjusted", contract_adjustment="alias 统一")
    results = [
        EvalResult(automated, True, "ok", [], False, False, 200, "sql", "passed", None, None, None, {}, "new_text2sql"),
        EvalResult(manual, True, "manual_review_required", [], True, False, 200, "sql", "passed", None, None, None, {}, "new_text2sql"),
        EvalResult(adjusted, True, "ok", [], False, False, 200, "sql", "passed", None, None, None, {}, "new_text2sql"),
    ]
    report_path = tmp_path / "m22-report.md"

    write_report(results, report_path)
    report = report_path.read_text(encoding="utf-8")

    assert "## M22 Contract Views" in report
    assert "automated_capability" in report
    assert "manual_or_diagnostic" in report
    assert "m22_adjusted" in report
    assert report.index("m22_adjusted") > report.index("## Score Summary")
