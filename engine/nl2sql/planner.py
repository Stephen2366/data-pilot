"""M10 QueryPlan / QueryPlanStep：SQL 生成前的结构化计划与自检。

★ 这一层像 Java 后端里的 DTO + Validator：LLM 先把“准备查什么”填进固定字段，
DataPilot 再检查表、字段、指标、Join 和敏感字段是否都来自可信上下文。真正执行 SQL 前
仍会经过 SQL Guard；planner 只是更早发现问题，不能替代最终安全门。
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import SchemaGraph
from engine.sql_guard.rbac import get_role_policy

PlanStepType = Literal["sql_query", "analysis", "rag_lookup"]

QUALIFIED_COLUMN_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")


class QueryPlanStep(BaseModel):
    """单个计划步骤，M10/M11 只执行 `step_type=sql_query` 的单步查询。
    通俗：QueryPlanStep 就是一个步骤的结构体——把一个查询步骤"长什么样"用字段定死了

    字段里保留 `depends_on` 和非 SQL step 类型，是为了后续 Hybrid / Data Analysis Agent
    能扩展 Plan-and-Execute；但 Phase 3A 的 validator 会拦截多个可执行 SQL step。
    """

    step_id: str = Field(description="稳定步骤 ID，例如 step_1；后续 trace 可用它做 parent_step_id。")
    step_index: int = Field(ge=1, description="从 1 开始的步骤序号，用于 trace_steps 排序。")
    step_type: PlanStepType = Field(default="sql_query", description="步骤类型；Phase 3A 只执行单个 sql_query。")
    purpose: str = Field(description="一步话说明本步骤要回答什么，不写原始 CoT 或详细推理。")
    depends_on: list[str] = Field(default_factory=list, description="依赖的 step_id 列表；单步 SQL 通常为空。")
    task_type: str = Field(default="aggregation", description="业务任务类型，例如 lookup、aggregation、ranking。")
    tables: list[str] = Field(default_factory=list, description="计划使用的物理表名，必须来自局部 SchemaGraph。")
    columns: list[str] = Field(default_factory=list, description="计划使用的字段，推荐写成 table.column。")
    metrics: list[str] = Field(default_factory=list, description="计划使用的指标 key，必须来自局部 SchemaGraph。")
    filters: list[str] = Field(default_factory=list, description="过滤条件摘要，只能引用局部 Schema 中的字段。")
    joins: list[str] = Field(default_factory=list, description="Join relation id 列表，必须来自 relations.yaml 构成的 JoinPath。")
    aggregations: list[str] = Field(default_factory=list, description="聚合表达式摘要，例如 SUM(order_items.line_amount)。")
    group_by: list[str] = Field(default_factory=list, description="分组字段，推荐写成 table.column。")
    order_by: list[str] = Field(default_factory=list, description="排序字段或输出别名，例如 item_gmv DESC。")
    limit: int | None = Field(default=None, ge=1, description="结果条数上限；没有 TopN 需求时可为空。")
    output_columns: list[str] = Field(
        default_factory=list,
        description=(
            "SQL 结果/API 展示列的精确集合与顺序；只写用户需要的列或显式别名，"
            "但不承担最终图表类型决策。"
        ),
    )
    output_expressions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "输出别名到可信表达式的显式绑定，例如 order_count -> COUNT(orders.id)；"
            "ORDER BY 使用聚合别名时必须填写，禁止让候选 SQL 自己解释计划别名。"
        ),
    )


class QueryPlan(BaseModel):
    """一次用户问题的结构化查询计划容器。"""

    steps: list[QueryPlanStep] = Field(min_length=1, description="计划步骤列表；Phase 3A 最多一个 sql_query step。")

    def to_human_explanation(self) -> str:
        """把结构化计划压成简短可读说明，供 trace / report 复用。"""

        parts = [f"{step.step_index}. {step.purpose}" for step in self.steps]
        return "\n".join(parts)


def normalize_base_aggregate_plan(plan: QueryPlan) -> tuple[QueryPlan, bool]:
    """移除上层 comparison completion 已负责的差额/变化率列。

    该函数只有收到服务端 ``base_aggregate_only`` authority 时才会被 pipeline 调用，避免
    改变 legacy Text2SQL 的直接比较合同。保留时间桶与基础指标，SQL 只负责产出可验证行。
    """

    derived_aliases = {"diff", "difference", "delta", "change", "change_rate", "growth_rate", "rate"}
    changed = False
    normalized_steps: list[QueryPlanStep] = []
    for step in plan.steps:
        removed = {
            value.rsplit(".", 1)[-1].strip().lower()
            for value in step.output_columns
            if value.rsplit(".", 1)[-1].strip().lower() in derived_aliases
        }
        if not removed:
            normalized_steps.append(step)
            continue
        retained_outputs = [
            value for value in step.output_columns
            if value.rsplit(".", 1)[-1].strip().lower() not in removed
        ]
        retained_bindings = {
            alias: expression for alias, expression in step.output_expressions.items()
            if alias.strip().lower() not in removed
        }
        retained_aggregations = [
            expression for alias, expression in retained_bindings.items()
            if alias.rsplit(".", 1)[-1].strip().lower() not in {"month", "period", "date", "year"}
        ]
        retained_order = [
            value for value in step.order_by
            if value.split()[0].rsplit(".", 1)[-1].strip().lower() not in removed
        ]
        normalized_steps.append(step.model_copy(update={
            "purpose": step.purpose + "；仅返回分组基础指标，由上层完成比较计算",
            "output_columns": retained_outputs,
            "output_expressions": retained_bindings,
            "aggregations": retained_aggregations,
            "order_by": retained_order,
        }))
        changed = True
    return QueryPlan(steps=normalized_steps), changed


class PlanValidationResult(BaseModel):
    """QueryPlan 自检结果，供 M11 trace 和 eval issue tags 复用。"""

    is_valid: bool
    issue_tags: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def query_plan_prompt_schema() -> str:
    """从 Pydantic Schema 自动生成给 LLM 的 JSON 格式说明。

    ★ 不手写示例的原因：字段增删时 prompt schema 会跟着模型定义更新，避免“代码一套、
    prompt 另一套”的漂移。
    """

    schema = QueryPlan.model_json_schema()
    return json.dumps(schema, ensure_ascii=False, indent=2)


def _append_issue(result: PlanValidationResult, issue_tag: str, error: str) -> None:
    """去重追加 issue tag，同时保留人能读懂的错误信息。"""

    if issue_tag not in result.issue_tags:
        result.issue_tags.append(issue_tag)
    result.errors.append(error)
    result.is_valid = False


def _allowed_columns(schema_graph: SchemaGraph) -> set[str]:
    """把局部 SchemaGraph 的字段扁平成 `table.column` 集合。"""

    return {f"{table}.{column}" for table, columns in schema_graph.fields.items() for column in columns}


def _join_relation_ids(schema_graph: SchemaGraph) -> set[str]:
    """收集局部 JoinPath 中允许使用的 relation id。"""

    relation_ids = {str(relation["id"]) for relation in schema_graph.relations if relation.get("id")}
    relation_ids.update(edge.relation_id for path in schema_graph.join_paths for edge in path.edges)
    return relation_ids


def _qualified_refs(values: list[str]) -> set[str]:
    """从过滤、聚合等自由文本摘要中提取 `table.column` 引用。"""

    refs: set[str] = set()
    for value in values:
        refs.update(f"{table}.{column}" for table, column in QUALIFIED_COLUMN_RE.findall(value))
    return refs


def _check_table_and_column_scope(
    *,
    step: QueryPlanStep,
    schema_graph: SchemaGraph,
    result: PlanValidationResult,
) -> None:
    """校验计划没有编造局部 SchemaGraph 之外的表字段。"""

    graph_tables = set(schema_graph.tables)
    graph_columns = _allowed_columns(schema_graph)

    for table in step.tables:
        if table not in graph_tables:
            _append_issue(result, "missing_table", f"{step.step_id} 引用了局部 Schema 中不存在的表：{table}")

    # ★ M12 修复：step.columns 里可能混入聚合表达式（如 COUNT(DISTINCT orders.id)），
    # 直接按 table.column 比对会误判为缺失字段。这里拆成两步：先把纯 table.column 挑出来，
    # 再从表达式里提取 table.column，两个集合合并后再校验。
    plain_columns = {col for col in step.columns if QUALIFIED_COLUMN_RE.fullmatch(col)}
    expr_columns = _qualified_refs(
        step.columns
        + step.filters
        + step.aggregations
        + step.group_by
        + step.order_by
        + step.output_columns
        + list(step.output_expressions.values())
    )
    explicit_columns = plain_columns | expr_columns
    for column in sorted(explicit_columns):
        if column not in graph_columns:
            _append_issue(result, "missing_column", f"{step.step_id} 引用了局部 Schema 中不存在的字段：{column}")


def _check_metric_scope(
    *,
    step: QueryPlanStep,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    result: PlanValidationResult,
) -> None:
    """校验指标既存在于领域定义，也被 M9 局部 Schema 召回。"""

    graph_metrics = set(schema_graph.metrics)
    for metric in step.metrics:
        if metric not in domain_schema.metrics or metric not in graph_metrics:
            _append_issue(result, "invalid_query_plan", f"{step.step_id} 引用了不可用指标：{metric}")


def _check_join_scope(*, step: QueryPlanStep, schema_graph: SchemaGraph, result: PlanValidationResult) -> None:
    """校验 Join 只能使用 M9 从 relations.yaml 生成的 relation id。"""

    relation_ids = _join_relation_ids(schema_graph)
    for join_id in step.joins:
        if join_id not in relation_ids:
            _append_issue(result, "invalid_join_path", f"{step.step_id} 引用了不可用 JoinPath：{join_id}")


def _check_output_bindings(*, step: QueryPlanStep, schema_graph: SchemaGraph, result: PlanValidationResult) -> None:
    """★ 校验输出 alias 绑定来自计划本身，避免候选 SQL 反过来解释计划。"""

    if step.step_type == "sql_query" and not step.output_columns:
        _append_issue(result, "invalid_query_plan", f"{step.step_id} 缺少精确输出列 output_columns。")
        return

    # 物理列可以直接作为 ORDER BY 名称；只有计划新造的聚合 alias 才必须显式绑定。
    # 例如 orders.created_at 不需要绑定，而 order_count 必须说明它等于哪个聚合表达式。
    output_names = {value.rsplit(".", 1)[-1] for value in step.output_columns}
    physical_names = {column for columns in schema_graph.fields.values() for column in columns}
    for alias in step.output_expressions:
        if alias not in output_names:
            _append_issue(result, "invalid_query_plan", f"{step.step_id} 的输出绑定 {alias} 不在 output_columns 中。")

    simple_order_pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:ASC|DESC)?\s*$", re.IGNORECASE)
    for order_item in step.order_by:
        match = simple_order_pattern.fullmatch(order_item)
        if match is None:
            continue
        name = match.group(1)
        if name in output_names and name not in physical_names and name not in step.output_expressions:
            _append_issue(
                result,
                "invalid_query_plan",
                f"{step.step_id} 的 ORDER BY 输出别名 {name} 缺少 output_expressions 绑定。",
            )


def _check_sensitive_fields(
    *,
    step: QueryPlanStep,
    domain_schema: DomainSchema,
    user_role: str,
    result: PlanValidationResult,
) -> None:
    """在 SQL 生成前预检敏感字段，但最终仍以 SQL Guard 为准。"""

    role_policy = get_role_policy(user_role)
    if role_policy is None:
        _append_issue(result, "invalid_query_plan", f"未知角色 {user_role}，无法校验计划。")
        return
    if role_policy.allow_sensitive_fields:
        return

    referenced_columns = set(step.columns) | _qualified_refs(
        step.filters
        + step.aggregations
        + step.group_by
        + step.order_by
        + step.output_columns
        + list(step.output_expressions.values())
    )
    sensitive_hits = sorted(referenced_columns & domain_schema.sensitive_fields)
    if sensitive_hits:
        _append_issue(
            result,
            "sensitive_field_access",
            f"{step.step_id} 计划访问敏感字段：{', '.join(sensitive_hits)}",
        )


def validate_query_plan(
    plan: QueryPlan,
    *,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    user_role: str,
) -> PlanValidationResult:
    """校验 QueryPlan 是否能进入后续 SQL 生成。

    M10 只做结构化自检：表、字段、指标、Join 必须来自 M9 局部 Schema；敏感字段提前拦截；
    多个可执行 SQL step 以 `unsupported_multi_step_plan` 暂停，留给后续 Plan-and-Execute。
    """

    result = PlanValidationResult(is_valid=True)

    # 步骤 1：先检查阶段边界，避免 M10 悄悄膨胀成多 SQL Agent。-------------------------
    sql_steps = [step for step in plan.steps if step.step_type == "sql_query"]
    if len(sql_steps) > 1:
        _append_issue(result, "unsupported_multi_step_plan", "Phase 3A 只允许一个可执行 sql_query step。")
    if not sql_steps:
        _append_issue(result, "invalid_query_plan", "QueryPlan 缺少可执行 sql_query step。")

    # 步骤 2：逐步校验局部 Schema 来源和安全预检。----------------------------------------
    for step in plan.steps:
        _check_table_and_column_scope(step=step, schema_graph=schema_graph, result=result)
        _check_metric_scope(step=step, schema_graph=schema_graph, domain_schema=domain_schema, result=result)
        _check_join_scope(step=step, schema_graph=schema_graph, result=result)
        _check_output_bindings(step=step, schema_graph=schema_graph, result=result)
        _check_sensitive_fields(step=step, domain_schema=domain_schema, user_role=user_role, result=result)

    return result
