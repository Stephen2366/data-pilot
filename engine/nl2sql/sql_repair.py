"""M44 SQL dialect repair 深模块。

调用方只选择服务端登记的策略并交付可信 QueryPlan 与 typed issue；本模块负责把
``llm_minimal / deterministic_ast / llm_enriched`` 的差异收在内部。无论采用哪种策略，
返回 SQL 都必须继续经过 pipeline 的 fidelity、SQL Guard 和真实执行，不能把 repair
本身当成安全证明。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from engine.nl2sql.generator import (
    GeneratedSQL,
    LLMEvidenceSink,
    LLMClient,
    generate_sql_repair_from_plan_step,
)
from engine.nl2sql.llm_call import LLMGenerationError
from engine.nl2sql.planner import QueryPlanStep
from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.objects import SchemaGraph

SQLRepairStrategy = Literal["llm_minimal", "deterministic_ast", "llm_enriched"]
_ALLOWED_STRATEGIES = frozenset({"llm_minimal", "deterministic_ast", "llm_enriched"})
_ALLOWED_ISSUE = "mysql_unsupported_date_trunc"


@dataclass(frozen=True)
class SQLRepairSnapshot:
    """首次失败执行签发的私有 repair authority，不进入 API/Trace 安全投影。

    QueryPlanStep 是第一次 SQL 生成前已经通过本地 validator 的同一对象。repair 若重新
    调模型生成另一份计划，就相当于修轮胎时偷偷换了目的地；所以 snapshot 必须不可变。
    """

    candidate_sql: str
    issue_code: str
    plan_step: QueryPlanStep

    def __post_init__(self) -> None:
        if self.issue_code != _ALLOWED_ISSUE:
            raise ValueError("sql_repair_issue_not_allowed")
        if not self.candidate_sql.strip():
            raise ValueError("sql_repair_candidate_missing")
        if self.plan_step.step_type != "sql_query":
            raise ValueError("sql_repair_plan_step_not_sql")


def validate_sql_repair_strategy(value: str) -> SQLRepairStrategy:
    """在服务端组装边界校验 closed-world strategy，拒绝静默 fallback。"""

    if value not in _ALLOWED_STRATEGIES:
        raise ValueError("sql_repair_strategy_not_allowed")
    return cast(SQLRepairStrategy, value)


def _deterministic_month_repair(candidate_sql: str, issue_code: str) -> GeneratedSQL:
    """用 SQLGlot AST 将精确月粒度 ``DATE_TRUNC`` 编译为 MySQL SQL。

    ★ 这里不做字符串替换：字符串替换可能误伤注释、字面量或嵌套表达式。只有单条
    SELECT 中、参数为字段的 month DATE_TRUNC 才准入；其他形状失败关闭。
    """

    if issue_code != _ALLOWED_ISSUE:
        raise LLMGenerationError(
            "SQL repair issue 不在允许列表。",
            stage="sql_repair",
            error_subtype="repair_issue_not_allowed",
        )
    try:
        statements = [item for item in sqlglot.parse(candidate_sql, read="mysql") if item is not None]
    except ParseError as exc:
        raise LLMGenerationError(
            "候选 SQL 无法解析，确定性 repair 已停止。",
            stage="sql_repair",
            error_subtype="repair_candidate_parse_failed",
        ) from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise LLMGenerationError(
            "确定性 repair 只接受单条 SELECT。",
            stage="sql_repair",
            error_subtype="repair_candidate_not_single_select",
        )

    statement = statements[0]
    date_trunc_nodes = list(statement.find_all(exp.DateTrunc))
    if not date_trunc_nodes:
        raise LLMGenerationError(
            "候选 SQL 不包含可修复的 DATE_TRUNC。",
            stage="sql_repair",
            error_subtype="repair_target_missing",
        )
    for node in date_trunc_nodes:
        unit = node.args.get("unit")
        source = node.this
        if not isinstance(unit, exp.Literal) or str(unit.this).lower() != "month":
            raise LLMGenerationError(
                "确定性 repair 只允许 month DATE_TRUNC。",
                stage="sql_repair",
                error_subtype="repair_unit_not_allowed",
            )
        if not isinstance(source, exp.Column):
            raise LLMGenerationError(
                "确定性 repair 只允许字段上的 DATE_TRUNC。",
                stage="sql_repair",
                error_subtype="repair_expression_not_allowed",
            )

    # SQLGlot 在 MySQL dialect 下把 DateTrunc 编译成 STR_TO_DATE + YEAR/MONTH；SELECT
    # projection、窗口表达式和 alias 都来自原 AST，因此不会像自由生成那样漏掉 diff 等列。
    repaired_sql = statement.sql(dialect="mysql")
    if "date_trunc" in repaired_sql.lower():
        raise LLMGenerationError(
            "DATE_TRUNC 未被完整编译，确定性 repair 已停止。",
            stage="sql_repair",
            error_subtype="repair_translation_incomplete",
        )
    tables = sorted({table.name for table in statement.find_all(exp.Table) if table.name})
    return GeneratedSQL(
        sql=repaired_sql,
        tables_used=tables,
        confidence=1.0,
        reasoning_summary="deterministic_ast_month_dialect_translation",
    )


def repair_sql_candidate(
    *,
    strategy: SQLRepairStrategy,
    question: str,
    user_role: str,
    plan_step: QueryPlanStep,
    schema_graph: SchemaGraph,
    domain_schema: DomainSchema,
    candidate_sql: str,
    issue_code: str,
    llm_client: LLMClient | None = None,
    llm_evidence_sink: LLMEvidenceSink | None = None,
) -> GeneratedSQL:
    """执行一种 closed-world repair；公共 Gate 由 pipeline 在返回后统一执行。"""

    selected = validate_sql_repair_strategy(strategy)
    if selected == "deterministic_ast":
        return _deterministic_month_repair(candidate_sql, issue_code)
    return generate_sql_repair_from_plan_step(
        question=question,
        user_role=user_role,
        plan_step=plan_step,
        schema_graph=schema_graph,
        domain_schema=domain_schema,
        candidate_sql=candidate_sql,
        issue_code=issue_code,
        llm_client=llm_client,
        llm_evidence_sink=llm_evidence_sink,
        include_required_outputs=selected == "llm_enriched",
    )
