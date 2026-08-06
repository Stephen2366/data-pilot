"""M4 Prompt Builder：把业务 Schema、KPI 和 few-shot 示例组装给 LLM。

Prompt 的职责是“尽量让模型生成好 SQL”；真正的安全门仍在 SQL Guard / RBAC。
"""

from __future__ import annotations

from engine.nl2sql.planner import QueryPlanStep, query_plan_prompt_schema
from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import JoinPath, SchemaGraph


def _format_tables(domain_schema: DomainSchema) -> str:
    """把可用表和字段说明压成 prompt 友好的文本。"""

    lines: list[str] = []
    for table in domain_schema.tables.values():
        lines.append(f"- 表 `{table.name}`：{table.business_meaning}")
        for field in table.fields.values():
            sensitive_note = "，敏感字段" if field.sensitivity == "sensitive" else ""
            lines.append(f"  - {table.name}.{field.name}：{field.meaning}；角色={field.semantic_role}{sensitive_note}")
    return "\n".join(lines)


def _format_metrics(domain_schema: DomainSchema) -> str:
    """把 KPI 口径写进 prompt，减少 GMV / 退款率这类业务词歧义。"""

    lines: list[str] = []
    for metric in domain_schema.metrics.values():
        filter_text = f"；过滤条件：{metric.filter}" if metric.filter else ""
        time_text = f"；默认时间字段：{metric.default_time_field}" if metric.default_time_field else ""
        lines.append(f"- {metric.name}（{metric.key}）：{metric.formula}{filter_text}{time_text}。{metric.description}")
    return "\n".join(lines)


def _format_examples(domain_schema: DomainSchema) -> str:
    """把 M3 模板 SQL 作为 few-shot 示例，沿用已验证口径。"""

    lines: list[str] = []
    for example in domain_schema.examples[:5]:
        lines.append(f"### few-shot {example.example_id}")
        lines.append(f"问题：{example.question}")
        lines.append("SQL：")
        lines.append(example.sql)
    return "\n".join(lines)


def build_sql_prompt(*, question: str, user_role: str, domain_schema: DomainSchema) -> str:
    """构造 M4 NL2SQL prompt。

    ★ 这里明确告诉模型输出 JSON，但后续仍会兼容 fenced SQL；因为真实 LLM 偶尔会不听话，
    不能让响应格式小波动直接拖垮主链路。
    """

    sensitive_fields = ", ".join(sorted(domain_schema.sensitive_fields)) or "无"
    return f"""你是 DataPilot 的 NL2SQL 生成器。请严格遵守：
1. 只生成单条 SELECT 查询；禁止 DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE。
2. 不要查询敏感字段。当前敏感字段：{sensitive_fields}。
3. 遵守用户角色 `{user_role}` 的权限边界；如果问题需要越权数据，也先生成最接近的安全 SELECT，后续 SQL Guard 会拦截。
4. SQL 使用 MySQL 兼容语法，尽量避免方言专属函数；日期范围使用明确字面值。
5. 只返回 JSON：{{"sql": "...", "tables_used": ["..."], "confidence": 0.0-1.0, "reasoning_summary": "一句话说明"}}。

可用表和字段：
{_format_tables(domain_schema)}

业务指标口径：
{_format_metrics(domain_schema)}

few-shot 示例：
{_format_examples(domain_schema)}

用户问题：{question}
"""


def _format_schema_graph(schema_graph: SchemaGraph) -> str:
    """把 M9 局部 SchemaGraph 压成 QueryPlan prompt 可读的上下文。"""

    lines: list[str] = []
    for table in schema_graph.tables:
        fields = ", ".join(schema_graph.fields.get(table, [])) or "无字段"
        lines.append(f"- 表 `{table}` 可用字段：{fields}")
    return "\n".join(lines)


def _format_plan_metrics(domain_schema_metrics: dict[str, object], schema_graph: SchemaGraph) -> str:
    """只展示局部 Schema 召回到的指标，避免计划引用全量 KPI 噪音。"""

    lines: list[str] = []
    for metric_key in schema_graph.metrics:
        metric = domain_schema_metrics.get(metric_key)
        if metric is None:
            continue
        name = getattr(metric, "name", metric_key)
        formula = getattr(metric, "formula", "")
        description = getattr(metric, "description", "")
        filter_rule = getattr(metric, "filter", "")
        time_field = getattr(metric, "default_time_field", "")
        filter_text = f"；附加过滤条件：{filter_rule}" if filter_rule else ""
        time_text = f"；默认时间字段：{time_field}" if time_field else ""
        lines.append(f"- {metric_key}（{name}）：{formula}{filter_text}{time_text}。{description}")
    return "\n".join(lines) or "无"


def _format_join_paths(join_paths: list[JoinPath]) -> str:
    """列出允许使用的 Join relation id，后续 validator 也按这些 id 校验。"""

    lines: list[str] = []
    for path in join_paths:
        for edge in path.edges:
            through = f"，桥表 {edge.through_table}" if edge.through_table else ""
            lines.append(
                f"- {edge.relation_id}: {edge.left_table}.{edge.left_column} -> "
                f"{edge.right_table}.{edge.right_column}（{edge.join_type}{through}）"
            )
    return "\n".join(lines) or "无"


def _format_query_plan_notes(question: str, schema_graph: SchemaGraph) -> str:
    """按问题意图给计划阶段补少量业务约束，优先约束高频易混的指标口径。"""

    notes: list[str] = []
    asks_sales_by_item = "商品销售额" in question
    asks_sales_by_category = "类目销售额" in question or "类目" in question and "销售额" in question
    # ★ M13 复盘出的高频漂移：模型看到“销售额”容易选全订单 GMV。
    # 这里只在局部 Schema 已召回 item_gmv 时提醒计划层，避免把业务规则写成全局硬编码。
    if "item_gmv" in schema_graph.metrics and (asks_sales_by_item or asks_sales_by_category):
        notes.append(
            "商品销售额/类目销售额必须使用 `item_gmv`，聚合 `order_items.line_amount`；"
            "不要用 `gmv` 或 `orders.order_amount` 代替。"
        )
    if asks_sales_by_item and {"order_items", "products"}.issubset(set(schema_graph.tables)):
        notes.append(
            "商品销售额 TopN 需要计划 `order_items` + `products`，通过 "
            "`order_items.product_id = products.id` 关联，输出商品名和 `item_gmv`。"
        )
    if asks_sales_by_category and {"order_items", "products", "product_categories"}.issubset(set(schema_graph.tables)):
        notes.append(
            "类目销售额排名需要计划 `order_items` + `products` + `product_categories`，通过 "
            "`order_items.product_id = products.id` 后再连类目，按一级类目输出和排序。"
        )
    if "各渠道订单量" in question and {"channels", "orders"}.issubset(set(schema_graph.tables)):
        notes.append(
            "各渠道订单量是可比较的聚合结果：按渠道分组后必须设置 "
            "`order_count DESC, channels.channel_name ASC`，保证首行和同分时的稳定顺序。"
        )
    if (
        "active" in question.lower()
        and "商品列表" in question
        and "products" in schema_graph.tables
        and {"product_name", "category", "status"}.issubset(set(schema_graph.fields.get("products", [])))
    ):
        notes.append("active 商品列表需要输出 `products.product_name`、`products.category`、`products.status`。")
    return "\n".join(f"- {note}" for note in notes) or "无"


def _format_sql_generation_notes(plan_step: QueryPlanStep, schema_graph: SchemaGraph) -> str:
    """根据计划和局部 Schema 给 SQL 生成阶段补少量硬约束，避免指标口径漂移。"""

    notes: list[str] = []
    if "item_gmv" in plan_step.metrics:
        notes.append("使用 `item_gmv` 时必须按局部指标公式聚合 `order_items.line_amount`，不要改用 `orders.order_amount`。")
    if (
        "item_gmv" in plan_step.metrics
        and "products" in schema_graph.tables
        and "order_items" in schema_graph.tables
        and "product_name_snapshot" in schema_graph.fields.get("order_items", [])
    ):
        notes.append("商品名输出优先 JOIN `products`；不要用 order_items.product_name_snapshot 替代 products。")
    if "item_gmv" in plan_step.metrics and "products" in schema_graph.tables and "order_items" in schema_graph.tables:
        notes.append("商品维度关联必须使用 `order_items.product_id = products.id`；不要用 orders.product_id 关联商品。")
    if "add_to_pay_conversion_rate" in plan_step.metrics:
        notes.append("转化率必须使用浮点除法，例如分子乘 `* 1.0` 或 `CAST(... AS REAL)`，不要让整数除法返回 0。")
    if "avg_selling_price" in plan_step.metrics:
        notes.append(
            "历史售价的时间窗口必须采用 overlap：`valid_from < 窗口结束`，且 "
            "`(valid_to IS NULL OR valid_to > 窗口开始)`；不能只按 valid_from 落在窗口内过滤。"
        )
    return "\n".join(f"- {note}" for note in notes) or "无"


def build_query_plan_prompt(
    *,
    question: str,
    schema_graph: SchemaGraph,
    metrics: dict[str, object],
    join_paths: list[JoinPath] | None = None,
) -> str:
    """构造 M10 QueryPlan prompt。

    ★ 这里明确禁止原始 CoT：计划层只要结构化字段和一句话 `purpose`，不要让模型把自由推理
    带进公开响应或后续 SQL prompt。
    """

    available_join_paths = join_paths if join_paths is not None else schema_graph.join_paths
    return f"""你是 DataPilot 的 QueryPlan 规划器。请严格遵守：
1. 只返回 JSON，不要返回 Markdown、解释文字或代码块。
2. 不要输出原始推理过程；每个 step 只用 `purpose` 写一句话意图摘要。
3. 表、字段、指标和 joins 必须只来自下面的局部 Schema；字段推荐写成 `table.column`。
4. Phase 3A 只允许一个 `step_type="sql_query"` 的可执行步骤；不要规划多个 SQL 查询。
5. `output_columns` 是 SQL 结果/API 展示列的精确合同：按用户需要的显示顺序填写，不能添加辅助列；ORDER BY 使用聚合输出别名时，必须在 `output_expressions` 写明 alias 到聚合表达式的绑定。
6. 展示图表类型不在本步骤决定，不要输出 display_type。

QueryPlan JSON Schema：
{query_plan_prompt_schema()}

局部表字段：
{_format_schema_graph(schema_graph)}

局部指标：
{_format_plan_metrics(metrics, schema_graph)}

允许的 JoinPath relation id：
{_format_join_paths(available_join_paths)}

计划补充约束：
{_format_query_plan_notes(question, schema_graph)}

用户问题：{question}
"""


def build_local_schema_sql_prompt(
    *,
    question: str,
    user_role: str,
    plan_step: QueryPlanStep,
    schema_graph: SchemaGraph,
    metrics: dict[str, object],
    join_paths: list[JoinPath] | None = None,
) -> str:
    """构造 M11 局部 Schema SQL prompt。

    ★ 和 M4 的全量 schema prompt 不同，这里只把 QueryPlanStep 已验证过的局部表字段、指标
    和 JoinPath 交给模型。这样 SQL 生成失败时也能归因：是检索/计划上下文不足，而不是全库
    prompt 噪音把模型带偏。
    """

    available_join_paths = join_paths if join_paths is not None else schema_graph.join_paths
    return f"""你是 DataPilot 的局部 Schema SQL 生成器。请严格遵守：
1. 只生成单条 SELECT 查询；禁止 DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE。
2. 只能使用下面局部 Schema、指标和 JoinPath 中出现的表字段；不得编造表、字段或关联关系。
3. 必须服务于 QueryPlanStep 的 `purpose`、`filters`、`aggregations`、`group_by`、`order_by` 和 `limit`；排序项、方向、先后顺序和条数上限都不能静默省略或改写。
4. SELECT 必须严格按照 `output_columns` 的集合与顺序输出；不得添加排序键、辅助列或其他未计划列，聚合结果应使用计划中的显式别名。
5. SQL 使用 MySQL 兼容语法；SQLite 只用于本地结果核对，不是生成方言合同。日期范围使用明确字面值。
6. 只返回 JSON：{{"sql": "...", "tables_used": ["..."], "confidence": 0.0-1.0, "reasoning_summary": "一句话说明"}}。

用户角色：{user_role}
用户问题：{question}

QueryPlanStep：
{plan_step.model_dump_json(ensure_ascii=False)}

局部表字段：
{_format_schema_graph(schema_graph)}

局部指标：
{_format_plan_metrics(metrics, schema_graph)}

允许的 JoinPath relation id：
{_format_join_paths(available_join_paths)}

SQL 生成补充约束：
{_format_sql_generation_notes(plan_step, schema_graph)}
"""
