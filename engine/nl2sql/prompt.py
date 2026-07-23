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
        lines.append(f"- {metric_key}（{name}）：{formula}。{description}")
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
5. 展示方式不在本步骤决定，不要输出 display_type。

QueryPlan JSON Schema：
{query_plan_prompt_schema()}

局部表字段：
{_format_schema_graph(schema_graph)}

局部指标：
{_format_plan_metrics(metrics, schema_graph)}

允许的 JoinPath relation id：
{_format_join_paths(available_join_paths)}

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
3. 必须服务于 QueryPlanStep 的 `purpose`、`filters`、`aggregations`、`group_by`、`order_by` 和 `limit`。
4. SQL 使用 MySQL 兼容语法，并尽量保持 SQLite 测试路径也能运行；日期范围使用明确字面值。
5. 只返回 JSON：{{"sql": "...", "tables_used": ["..."], "confidence": 0.0-1.0, "reasoning_summary": "一句话说明"}}。

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
"""
