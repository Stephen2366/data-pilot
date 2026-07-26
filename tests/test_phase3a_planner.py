"""Phase 3A M10 QueryPlanStep 与自检测试。

★ M10 的重点是把“模型想查什么”先变成可校验的结构化计划，再交给 M11 生成 SQL。
这些测试故意不调用真实 LLM：先把计划结构、安全预检和局部 Schema 边界固定住。
"""

import json

import pytest

from engine.nl2sql.generator import (
    QueryPlanExtractionError,
    extract_query_plan,
    generate_query_plan,
    generate_sql_from_plan_step,
)
from engine.nl2sql.planner import QueryPlan, QueryPlanStep, validate_query_plan
from engine.nl2sql.prompt import build_local_schema_sql_prompt, build_query_plan_prompt
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.objects import JoinEdge, JoinPath, SchemaGraph


def _sample_schema_graph() -> SchemaGraph:
    """构造一个最小局部 SchemaGraph，模拟 M9 召回后的多表商品 GMV 场景。"""

    relations = [
        {"id": "order_items_order", "from_table": "order_items", "to_table": "orders"},
        {"id": "order_items_product", "from_table": "order_items", "to_table": "products"},
    ]
    return SchemaGraph(
        tables=["order_items", "orders", "products"],
        fields={
            "orders": ["id", "order_status", "paid_at"],
            "order_items": ["id", "order_id", "product_id", "line_amount"],
            "products": ["id", "name"],
        },
        metrics=["item_gmv"],
        relations=relations,
        join_paths=[
            JoinPath(
                tables=["order_items", "orders", "products"],
                edges=[
                    JoinEdge(
                        relation_id="order_items_order",
                        left_table="order_items",
                        left_column="order_id",
                        right_table="orders",
                        right_column="id",
                        join_type="inner",
                    ),
                    JoinEdge(
                        relation_id="order_items_product",
                        left_table="order_items",
                        left_column="product_id",
                        right_table="products",
                        right_column="id",
                        join_type="inner",
                    ),
                ],
            )
        ],
    )


def _valid_step(**overrides: object) -> QueryPlanStep:
    """生成一条合法 sql_query step，非法场景只覆盖自己关心的字段。"""

    payload = {
        "step_id": "step_1",
        "step_index": 1,
        "step_type": "sql_query",
        "purpose": "按商品统计已支付订单的商品维度 GMV。",
        "depends_on": [],
        "task_type": "aggregation",
        "tables": ["orders", "order_items", "products"],
        "columns": ["orders.paid_at", "orders.order_status", "order_items.line_amount", "products.name"],
        "metrics": ["item_gmv"],
        "filters": ["orders.order_status NOT IN ('cancelled', 'canceled')"],
        "joins": ["order_items_order", "order_items_product"],
        "aggregations": ["SUM(order_items.line_amount)"],
        "group_by": ["products.name"],
        "order_by": ["item_gmv DESC"],
        "limit": 10,
        "output_columns": ["products.name", "item_gmv"],
    }
    payload.update(overrides)
    return QueryPlanStep(**payload)


def test_query_plan_step_parses_from_json_and_validates_against_schema_graph() -> None:
    """合法计划必须能从 JSON 解析，并且所有表、字段、指标、Join 都来自局部 Schema。"""

    raw_json = json.dumps({"steps": [_valid_step().model_dump()]}, ensure_ascii=False)
    plan = QueryPlan.model_validate_json(raw_json)
    result = validate_query_plan(
        plan,
        schema_graph=_sample_schema_graph(),
        domain_schema=load_domain_schema(),
        user_role="ops",
    )

    assert plan.steps[0].purpose
    assert result.is_valid
    assert result.issue_tags == []
    assert result.errors == []


def test_multiple_sql_query_steps_are_rejected_for_phase3a() -> None:
    """结构预留多 step，但 Phase 3A 不能真的执行多条 SQL。"""

    plan = QueryPlan(steps=[_valid_step(step_id="step_1"), _valid_step(step_id="step_2", step_index=2)])
    result = validate_query_plan(
        plan,
        schema_graph=_sample_schema_graph(),
        domain_schema=load_domain_schema(),
        user_role="ops",
    )

    assert not result.is_valid
    assert "unsupported_multi_step_plan" in result.issue_tags


@pytest.mark.parametrize(
    ("step", "issue_tag"),
    [
        (_valid_step(tables=["orders", "not_a_table"]), "missing_table"),
        (_valid_step(columns=["orders.not_a_column"]), "missing_column"),
        (_valid_step(metrics=["not_a_metric"]), "invalid_query_plan"),
        (_valid_step(joins=["orders_user"]), "invalid_join_path"),
    ],
)
def test_plan_validation_rejects_objects_outside_schema_graph(step: QueryPlanStep, issue_tag: str) -> None:
    """表、字段、指标和 Join 不能脱离 M9 的局部 SchemaGraph。"""

    result = validate_query_plan(
        QueryPlan(steps=[step]),
        schema_graph=_sample_schema_graph(),
        domain_schema=load_domain_schema(),
        user_role="ops",
    )

    assert not result.is_valid
    assert issue_tag in result.issue_tags


def test_sensitive_field_plan_is_blocked_before_sql_generation() -> None:
    """普通运营角色计划查询敏感字段时，要在 SQL 生成前被预检拦截。"""

    graph = _sample_schema_graph()
    graph = SchemaGraph(
        tables=[*graph.tables, "users"],
        fields={**graph.fields, "users": ["id", "email"]},
        metrics=graph.metrics,
        relations=graph.relations,
        join_paths=graph.join_paths,
    )
    result = validate_query_plan(
        QueryPlan(steps=[_valid_step(tables=["users"], columns=["users.email"], joins=[], metrics=[])]),
        schema_graph=graph,
        domain_schema=load_domain_schema(),
        user_role="ops",
    )

    assert not result.is_valid
    assert "sensitive_field_access" in result.issue_tags


def test_extract_query_plan_supports_fenced_json_and_maps_failures() -> None:
    """LLM 偶尔会包 markdown fenced block；完全不可解析时必须映射 invalid_query_plan。"""

    raw = "```json\n" + json.dumps({"steps": [_valid_step().model_dump()]}, ensure_ascii=False) + "\n```"

    plan = extract_query_plan(raw)

    assert plan.steps[0].step_id == "step_1"
    with pytest.raises(QueryPlanExtractionError) as exc_info:
        extract_query_plan("我无法生成计划。")
    assert exc_info.value.issue_tag == "invalid_query_plan"


def test_build_query_plan_prompt_uses_generated_schema_and_hides_cot() -> None:
    """Plan prompt 要从 Pydantic 字段生成 JSON 说明，且不能要求模型输出 CoT。"""

    prompt = build_query_plan_prompt(
        question="按商品统计 GMV Top10",
        schema_graph=_sample_schema_graph(),
        metrics=load_domain_schema().metrics,
        join_paths=_sample_schema_graph().join_paths,
    )

    assert "只返回 JSON" in prompt
    assert "steps" in prompt
    assert "purpose" in prompt
    assert "item_gmv" in prompt
    assert "order_items_order" in prompt
    assert "thoughts" not in prompt.lower()


def test_query_plan_prompt_includes_metric_filter_and_default_time_field() -> None:
    """局部指标 prompt 必须带上 filter/time_field，否则 GMV 时间口径会让模型猜。"""

    schema_graph = SchemaGraph(
        tables=["orders"],
        fields={"orders": ["id", "order_amount", "order_status", "paid_at", "created_at"]},
        metrics=["gmv"],
        relations=[],
        join_paths=[],
    )

    prompt = build_query_plan_prompt(
        question="2026 年 6 月 GMV 是多少？",
        schema_graph=schema_graph,
        metrics=load_domain_schema().metrics,
        join_paths=[],
    )

    assert "orders.paid_at" in prompt
    assert "orders.order_status NOT IN ('cancelled', 'canceled')" in prompt
    assert "orders.paid_at IS NOT NULL" in prompt


def test_query_plan_prompt_guides_product_and_category_sales_to_item_gmv() -> None:
    """商品/类目销售额问题要在计划层优先锁定 item_gmv，避免后续 SQL 被 orders.gmv 带偏。"""

    graph = SchemaGraph(
        tables=["order_items", "orders", "products", "product_categories"],
        fields={
            "orders": ["id", "order_amount", "order_status", "paid_at"],
            "order_items": ["order_id", "product_id", "line_amount"],
            "products": ["id", "product_name", "category_id"],
            "product_categories": ["id", "name", "level"],
        },
        metrics=["gmv", "item_gmv"],
        relations=[],
        join_paths=[],
    )

    prompt = build_query_plan_prompt(
        question="一级类目销售额排名",
        schema_graph=graph,
        metrics=load_domain_schema().metrics,
        join_paths=[],
    )

    assert "商品销售额/类目销售额" in prompt
    assert "item_gmv" in prompt
    assert "order_items.line_amount" in prompt
    assert "order_items.product_id" in prompt
    assert "products" in prompt
    assert "product_categories" in prompt
    assert "不要用 `gmv` 或 `orders.order_amount` 代替" in prompt


def test_query_plan_prompt_guides_active_product_list_columns() -> None:
    """active 商品列表在评测中需要输出商品名、类目和状态，计划层要把这些列写清楚。"""

    graph = SchemaGraph(
        tables=["products"],
        fields={"products": ["id", "product_name", "category", "status", "price"]},
        metrics=[],
        relations=[],
        join_paths=[],
    )

    prompt = build_query_plan_prompt(
        question="查询 active 商品列表前 10 条",
        schema_graph=graph,
        metrics=load_domain_schema().metrics,
        join_paths=[],
    )

    assert "products.product_name" in prompt
    assert "products.category" in prompt
    assert "products.status" in prompt


class _CapturingSystemPromptClient:
    """记录 generator 传入的 system prompt，避免不同 LLM 任务共用错角色。"""

    def __init__(self) -> None:
        self.system_prompts: list[str | None] = []

    def complete(self, *, prompt: str, system_prompt: str | None = None) -> str:
        self.system_prompts.append(system_prompt)
        if "QueryPlan JSON Schema" in prompt:
            return json.dumps({"steps": [_valid_step().model_dump()]}, ensure_ascii=False)
        return json.dumps(
            {
                "sql": "SELECT SUM(order_amount) AS gmv FROM orders",
                "tables_used": ["orders"],
                "confidence": 0.8,
                "reasoning_summary": "测试捕获 system prompt。",
            },
            ensure_ascii=False,
        )


def test_generator_passes_task_specific_system_prompts() -> None:
    """QueryPlan 和 SQL 生成是不同任务，不能共用“只负责转 SQL”的 system prompt。"""

    client = _CapturingSystemPromptClient()
    domain_schema = load_domain_schema()

    generate_query_plan(
        question="按商品统计 GMV Top10",
        schema_graph=_sample_schema_graph(),
        domain_schema=domain_schema,
        llm_client=client,
    )
    generate_sql_from_plan_step(
        question="按商品统计 GMV Top10",
        user_role="ops",
        plan_step=_valid_step(),
        schema_graph=_sample_schema_graph(),
        domain_schema=domain_schema,
        llm_client=client,
    )

    assert client.system_prompts[0]
    assert "查询规划器" in client.system_prompts[0]
    assert client.system_prompts[1]
    assert "SQL 生成器" in client.system_prompts[1]
    assert client.system_prompts[0] != client.system_prompts[1]


def test_local_schema_sql_prompt_guides_item_gmv_to_products_join() -> None:
    """商品维度 GMV 要提醒模型优先 JOIN products，避免用快照字段绕开已召回表。"""

    graph = _sample_schema_graph()
    graph = SchemaGraph(
        tables=graph.tables,
        fields={
            **graph.fields,
            "order_items": [*graph.fields["order_items"], "product_name_snapshot"],
            "products": [*graph.fields["products"], "product_name"],
        },
        metrics=graph.metrics,
        relations=graph.relations,
        join_paths=graph.join_paths,
    )
    prompt = build_local_schema_sql_prompt(
        question="2026 年 6 月商品销售额 Top 5",
        user_role="ops",
        plan_step=_valid_step(metrics=["item_gmv"], output_columns=["products.name", "item_gmv"]),
        schema_graph=graph,
        metrics=load_domain_schema().metrics,
        join_paths=graph.join_paths,
    )

    assert "item_gmv" in prompt
    assert "products" in prompt
    assert "product_name_snapshot" in prompt
    assert "不要用 order_items.product_name_snapshot 替代 products" in prompt
    assert "order_items.product_id = products.id" in prompt
    assert "不要用 orders.product_id" in prompt


def test_local_schema_sql_prompt_guides_conversion_rate_to_float_division() -> None:
    """转化率这类比例指标必须提醒模型做浮点除法，否则 SQLite 会把 7/10 算成 0。"""

    graph = SchemaGraph(
        tables=["user_behavior_log"],
        fields={"user_behavior_log": ["device_type", "event_type"]},
        metrics=["add_to_pay_conversion_rate"],
        relations=[],
        join_paths=[],
    )
    prompt = build_local_schema_sql_prompt(
        question="哪个设备类型加购到支付转化率最高？",
        user_role="ops",
        plan_step=_valid_step(
            tables=["user_behavior_log"],
            columns=["user_behavior_log.device_type", "user_behavior_log.event_type"],
            metrics=["add_to_pay_conversion_rate"],
            joins=[],
            output_columns=["device_type", "conversion_rate"],
        ),
        schema_graph=graph,
        metrics=load_domain_schema().metrics,
        join_paths=[],
    )

    assert "浮点除法" in prompt
    assert "* 1.0" in prompt or "CAST" in prompt
