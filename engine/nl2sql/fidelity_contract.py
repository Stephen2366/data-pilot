"""M24 QueryPlan → SQL 语义保真合同。

这个 module 的 seam 很小：调用方交付已验证的 ``QueryPlanStep``、候选只读 SQL、可信
``DomainSchema`` 和生成 dialect，就拿回统一的 ``passed / failed / indeterminate`` 与可复演
证据。表别名、SELECT alias、限定名消歧、排序方向、limit 和输出投影等复杂度全部收在这里，
避免 generator / pipeline / eval 各自维护一套“什么算等价”。

★ 合同只验证，不改写 SQL。``indeterminate`` 也不是“差不多正确”，调用方必须保守阻断。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any, Literal

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import DomainSchema

ContractStatus = Literal["passed", "failed", "indeterminate"]
IssueCategory = Literal["order_by", "limit", "projection", "parser"]


@dataclass(frozen=True)
class FidelityIssue:
    """单个保真问题；稳定 ``code`` 供 trace / triage 聚合，message 供人阅读。"""

    category: IssueCategory
    code: str
    message: str


@dataclass(frozen=True)
class SQLPlanFidelityResult:
    """深 module 的唯一结果模型，也是 pipeline 与 focused tests 的共同观察面。"""

    status: ContractStatus
    dialect: str
    issues: tuple[FidelityIssue, ...] = ()
    planned_order_by: tuple[str, ...] = ()
    observed_order_by: tuple[str, ...] = ()
    normalized_planned_order_by: tuple[str, ...] = ()
    normalized_observed_order_by: tuple[str, ...] = ()
    planned_limit: int | None = None
    observed_limit: int | None = None
    planned_output_columns: tuple[str, ...] = ()
    observed_output_columns: tuple[str, ...] = ()
    planned_output_bindings: dict[str, str] = field(default_factory=dict)
    observed_output_bindings: dict[str, str] = field(default_factory=dict)
    alias_bindings: dict[str, str] = field(default_factory=dict)
    normalized_sql: str | None = None
    candidate_sql: str = ""
    candidate_sql_hash: str = ""
    evidence_level: str = "full"

    @property
    def passed(self) -> bool:
        """调用方只需读一个布尔值；失败细节仍完整留在 result 内。"""

        return self.status == "passed"

    @property
    def reason_code(self) -> str:
        """返回首个稳定 reason code；无问题时固定为 ``fidelity_ok``。"""

        return self.issues[0].code if self.issues else "fidelity_ok"

    def to_trace_metadata(self) -> dict[str, Any]:
        """转成 JSONL / LangFuse 都可序列化的完整证据，不再只保存 300 字 preview。"""

        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        payload["comparison_rule"] = "sqlglot_ast_semantic_fidelity"
        payload["contract_status"] = self.status
        payload["reason_code"] = self.reason_code
        payload["candidate_sql_preview"] = self.candidate_sql[:300]
        return payload


class _IndeterminateExpression(ValueError):
    """内部控制流：当前 scope 无法唯一证明表达式指向，不向 caller 暴露。"""


def evaluate_sql_plan_fidelity(
    *,
    plan_step: QueryPlanStep,
    candidate_sql: str,
    domain_schema: DomainSchema,
    dialect: str = "mysql",
) -> SQLPlanFidelityResult:
    """只读比较 QueryPlan 与候选 SQL，并返回结构化判定与证据。

    首版支持历史 trace 已证明需要的四类等价：表别名、quoted identifier、当前 SELECT
    scope 内唯一的限定名省略、同 scope SELECT 输出 alias。跨 derived scope 的字段解析、
    ordinal order、参数 / offset limit 都返回 ``indeterminate``，绝不靠猜测放行。
    """

    sql_hash = sha256(candidate_sql.encode("utf-8")).hexdigest()
    try:
        statements = sqlglot.parse(candidate_sql, read=dialect)
    except sqlglot.errors.SqlglotError as exc:
        return _parser_result(
            plan_step=plan_step,
            candidate_sql=candidate_sql,
            sql_hash=sql_hash,
            dialect=dialect,
            code="sql_parse_error",
            message=f"候选 SQL 无法按 {dialect} dialect 解析：{exc}",
        )
    if len(statements) != 1:
        return _parser_result(
            plan_step=plan_step,
            candidate_sql=candidate_sql,
            sql_hash=sql_hash,
            dialect=dialect,
            code="multiple_statements_not_supported",
            message="保真合同只接受单条 SQL。",
        )

    statement = statements[0]
    root_scope = build_scope(statement)
    if root_scope is None or not isinstance(root_scope.expression, exp.Select):
        return _parser_result(
            plan_step=plan_step,
            candidate_sql=candidate_sql,
            sql_hash=sql_hash,
            dialect=dialect,
            code="top_level_select_required",
            message="保真合同首版只验证顶层 SELECT scope。",
        )

    select = root_scope.expression
    alias_bindings, physical_tables, has_derived_source = _scope_sources(root_scope)
    select_aliases = {item.alias: item.this for item in select.expressions if item.alias}
    plan_aliases, plan_alias_issue = _parse_plan_alias_bindings(plan_step, dialect=dialect)
    issues: list[FidelityIssue] = []
    if plan_alias_issue is not None:
        issues.append(plan_alias_issue)
    planned_normalized: list[str] = []
    observed_normalized: list[str] = []

    # 步骤 1：严格比较 ORDER BY ============================================================
    observed_order = select.args.get("order")
    observed_items = list(observed_order.expressions) if observed_order is not None else []
    if len(plan_step.order_by) != len(observed_items):
        code = "missing_order_by" if plan_step.order_by and not observed_items else "order_item_count_mismatch"
        issues.append(
            FidelityIssue(
                category="order_by",
                code=code,
                message=f"ORDER BY 计划排序项 {len(plan_step.order_by)} 个，SQL 实际 {len(observed_items)} 个。",
            )
        )
    else:
        for index, (planned_text, observed_ordered) in enumerate(zip(plan_step.order_by, observed_items, strict=True)):
            try:
                planned_ordered = _parse_order_item(planned_text, dialect=dialect)
            except _IndeterminateExpression as exc:
                issues.append(FidelityIssue("parser", "invalid_planned_order_expression", str(exc)))
                continue
            if isinstance(observed_ordered.this, exp.Literal) and observed_ordered.this.is_int:
                issues.append(
                    FidelityIssue("parser", "ordinal_order_not_supported", f"第 {index + 1} 个排序项使用 ORDER BY 序号。")
                )
                continue
            try:
                planned_expr = _normalize_expression(
                    planned_ordered.this,
                    # ★ 计划表达式只能由 QueryPlan 自己解释。若借候选 SQL 的 SELECT alias
                    # 反解，错误 SQL 也能“自证”它对计划是忠实的。
                    select_aliases=plan_aliases,
                    alias_bindings=alias_bindings,
                    physical_tables=physical_tables,
                    domain_schema=domain_schema,
                    has_derived_source=has_derived_source,
                    dialect=dialect,
                )
                observed_expr = _normalize_expression(
                    observed_ordered.this,
                    select_aliases=select_aliases,
                    alias_bindings=alias_bindings,
                    physical_tables=physical_tables,
                    domain_schema=domain_schema,
                    has_derived_source=has_derived_source,
                    dialect=dialect,
                )
            except _IndeterminateExpression as exc:
                issues.append(FidelityIssue("parser", "ambiguous_order_expression", str(exc)))
                continue
            planned_normalized.append(planned_expr)
            observed_normalized.append(observed_expr)
            if planned_expr != observed_expr:
                issues.append(
                    FidelityIssue(
                        "order_by",
                        "order_expression_or_sequence_mismatch",
                        f"第 {index + 1} 个排序表达式不等价：{planned_expr} != {observed_expr}。",
                    )
                )
            if bool(planned_ordered.args.get("desc")) != bool(observed_ordered.args.get("desc")):
                issues.append(
                    FidelityIssue("order_by", "order_direction_mismatch", f"第 {index + 1} 个排序方向不一致。")
                )

    # 步骤 2：严格比较 LIMIT ===============================================================
    observed_limit, limit_issue = _extract_limit(select)
    if limit_issue is not None:
        issues.append(limit_issue)
    elif plan_step.limit != observed_limit:
        issues.append(
            FidelityIssue(
                "limit",
                "limit_mismatch",
                f"计划 LIMIT={plan_step.limit}，SQL 实际 LIMIT={observed_limit}。",
            )
        )

    # 步骤 3：精确比较输出投影与展示顺序 ===================================================
    planned_output = tuple(_planned_output_name(item, dialect=dialect) for item in plan_step.output_columns)
    observed_output, output_issue = _select_output_names(select, dialect=dialect)
    if output_issue is not None:
        issues.append(output_issue)
    elif planned_output:
        issues.extend(_projection_issues(planned_output, observed_output))

    status: ContractStatus
    if any(issue.category != "parser" for issue in issues):
        status = "failed"
    elif issues:
        status = "indeterminate"
    else:
        status = "passed"
    return SQLPlanFidelityResult(
        status=status,
        dialect=dialect,
        issues=tuple(issues),
        planned_order_by=tuple(plan_step.order_by),
        observed_order_by=tuple(item.sql(dialect=dialect) for item in observed_items),
        normalized_planned_order_by=tuple(planned_normalized),
        normalized_observed_order_by=tuple(observed_normalized),
        planned_limit=plan_step.limit,
        observed_limit=observed_limit,
        planned_output_columns=planned_output,
        observed_output_columns=observed_output,
        planned_output_bindings=dict(plan_step.output_expressions),
        observed_output_bindings={
            alias: expression.sql(dialect=dialect, normalize=True) for alias, expression in select_aliases.items()
        },
        alias_bindings=alias_bindings,
        normalized_sql=statement.sql(dialect=dialect, normalize=True),
        candidate_sql=candidate_sql,
        candidate_sql_hash=sql_hash,
    )


def _scope_sources(root_scope: Scope) -> tuple[dict[str, str], set[str], bool]:
    """只读取顶层 SELECT sources；不把 CTE 内部表错误当成本 scope 的消歧候选。"""

    bindings: dict[str, str] = {}
    physical_tables: set[str] = set()
    has_derived_source = False
    for alias, (_, source) in root_scope.selected_sources.items():
        if isinstance(source, exp.Table):
            bindings[alias] = source.name
            bindings[source.name] = source.name
            physical_tables.add(source.name)
        else:
            bindings[alias] = "<derived_scope>"
            has_derived_source = True
    return bindings, physical_tables, has_derived_source


def _parse_order_item(text: str, *, dialect: str) -> exp.Ordered:
    """借助 parser 读取单个 QueryPlan 排序项，避免继续写字符串拆分器。"""

    try:
        statement = sqlglot.parse_one(f"SELECT 1 ORDER BY {text}", read=dialect)
    except sqlglot.errors.SqlglotError as exc:
        raise _IndeterminateExpression(f"QueryPlan 排序项无法解析：{text}（{exc}）") from exc
    order = statement.args.get("order")
    if order is None or len(order.expressions) != 1:
        raise _IndeterminateExpression(f"QueryPlan 排序项不是单一表达式：{text}")
    return order.expressions[0]


def _parse_plan_alias_bindings(
    plan_step: QueryPlanStep,
    *,
    dialect: str,
) -> tuple[dict[str, exp.Expression], FidelityIssue | None]:
    """把 QueryPlan 明示的 alias→expression 解析为 AST；绑定本身不可信时保守退出。"""

    bindings: dict[str, exp.Expression] = {}
    for alias, expression_text in plan_step.output_expressions.items():
        try:
            parsed = sqlglot.parse_one(f"SELECT {expression_text}", read=dialect)
        except sqlglot.errors.SqlglotError as exc:
            return {}, FidelityIssue(
                "parser",
                "invalid_plan_output_binding",
                f"QueryPlan 输出别名 {alias} 的表达式无法解析：{exc}",
            )
        forbidden_clauses = ("from_", "where", "group", "having", "qualify", "order", "limit", "offset")
        if (
            not isinstance(parsed, exp.Select)
            or len(parsed.expressions) != 1
            or any(parsed.args.get(name) is not None for name in forbidden_clauses)
        ):
            return {}, FidelityIssue(
                "parser",
                "invalid_plan_output_binding",
                f"QueryPlan 输出别名 {alias} 必须绑定单一表达式。",
            )
        bindings[alias] = parsed.expressions[0]
    return bindings, None


def _normalize_expression(
    expression: exp.Expression,
    *,
    select_aliases: dict[str, exp.Expression],
    alias_bindings: dict[str, str],
    physical_tables: set[str],
    domain_schema: DomainSchema,
    has_derived_source: bool,
    dialect: str,
) -> str:
    """把表达式归一到 base-table qualified AST；无法唯一绑定就显式退出。"""

    node = expression.copy()
    if isinstance(node, exp.Column) and not node.table and node.name in select_aliases:
        node = select_aliases[node.name].copy()
    for identifier in node.find_all(exp.Identifier):
        identifier.set("quoted", False)
    for column in node.find_all(exp.Column):
        if column.table:
            resolved_table = alias_bindings.get(column.table, column.table)
            if resolved_table == "<derived_scope>":
                raise _IndeterminateExpression(f"跨 derived scope 字段无法证明等价：{column.sql()}。")
            column.set("table", exp.to_identifier(resolved_table))
            continue
        candidates = [
            table_name
            for table_name in physical_tables
            if table_name in domain_schema.tables and column.name in domain_schema.tables[table_name].fields
        ]
        if len(candidates) == 1:
            column.set("table", exp.to_identifier(candidates[0]))
            continue
        if has_derived_source:
            raise _IndeterminateExpression(f"无前缀字段 {column.name} 可能来自 derived scope。")
        raise _IndeterminateExpression(f"无前缀字段 {column.name} 在当前 scope 不是唯一可解析字段。")
    return node.sql(dialect=dialect, normalize=True)


def _extract_limit(select: exp.Select) -> tuple[int | None, FidelityIssue | None]:
    """首版只接受简单整数字面量；offset / 参数留待真实需求出现后扩展。"""

    limit = select.args.get("limit")
    offset = select.args.get("offset")
    if offset is not None:
        return None, FidelityIssue("parser", "offset_limit_not_supported", "M24 首版不接受 LIMIT/OFFSET 形式。")
    if limit is None:
        return None, None
    value = limit.expression
    if not isinstance(value, exp.Literal) or not value.is_int:
        return None, FidelityIssue("parser", "nonliteral_limit_not_supported", "M24 首版只接受整数字面量 LIMIT。")
    return int(value.this), None


def _planned_output_name(text: str, *, dialect: str) -> str:
    """把 ``table.column`` 计划输出压成真实结果列名，同时保留明确输出 alias。"""

    try:
        item = sqlglot.parse_one(f"SELECT {text}", read=dialect).expressions[0]
    except sqlglot.errors.SqlglotError:
        return text
    return item.alias_or_name or item.sql(dialect=dialect, normalize=True)


def _select_output_names(select: exp.Select, *, dialect: str) -> tuple[tuple[str, ...], FidelityIssue | None]:
    """提取 SQL 的确定输出顺序；``*`` 无法证明精确投影，因此保守返回 indeterminate。"""

    names: list[str] = []
    for item in select.expressions:
        if isinstance(item, exp.Star) or (isinstance(item, exp.Column) and isinstance(item.this, exp.Star)):
            return (), FidelityIssue("parser", "star_projection_not_supported", "精确投影合同不接受 SELECT *。")
        output_name = item.alias_or_name
        if not output_name:
            return (), FidelityIssue(
                "parser",
                "unnamed_projection_not_supported",
                f"输出表达式缺少稳定列名：{item.sql(dialect=dialect)}。",
            )
        names.append(output_name)
    return tuple(names), None


def _projection_issues(planned: tuple[str, ...], observed: tuple[str, ...]) -> list[FidelityIssue]:
    """精确区分 extra/missing/name 与纯展示顺序差异。"""

    if planned == observed:
        return []
    if Counter(planned) == Counter(observed):
        return [
            FidelityIssue(
                "projection",
                "projection_order_mismatch",
                f"输出列集合相同但展示顺序不同：计划 {list(planned)}，SQL {list(observed)}。",
            )
        ]
    missing = list((Counter(planned) - Counter(observed)).elements())
    extra = list((Counter(observed) - Counter(planned)).elements())
    return [
        FidelityIssue(
            "projection",
            "projection_set_mismatch",
            f"输出投影不一致：missing={missing}，extra={extra}。",
        )
    ]


def _parser_result(
    *,
    plan_step: QueryPlanStep,
    candidate_sql: str,
    sql_hash: str,
    dialect: str,
    code: str,
    message: str,
) -> SQLPlanFidelityResult:
    """统一构造 parse / top-scope 失败结果，保证 trace 字段不因失败路径缺失。"""

    return SQLPlanFidelityResult(
        status="indeterminate",
        dialect=dialect,
        issues=(FidelityIssue("parser", code, message),),
        planned_order_by=tuple(plan_step.order_by),
        planned_limit=plan_step.limit,
        planned_output_columns=tuple(_planned_output_name(item, dialect=dialect) for item in plan_step.output_columns),
        planned_output_bindings=dict(plan_step.output_expressions),
        candidate_sql=candidate_sql,
        candidate_sql_hash=sql_hash,
    )
