"""SQL Guard v0：用 sqlglot AST 拦截非 SELECT SQL。

★ 安全能力不能只靠 prompt。即使 M3 还没有 LLM，也先把 SQL 执行入口统一套上
AST 级只读检查，后续模板 SQL 和 LLM SQL 都走同一扇门。
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class GuardResult:
    """SQL Guard 校验结果。

    `is_allowed=False` 时，调用方只能返回结构化拦截信息，不能继续执行数据库查询。
    """

    is_allowed: bool
    blocked_reason: str | None = None


def validate_readonly_sql(sql: str) -> GuardResult:
    """只允许单条 SELECT 查询通过。

    M3 范围刻意保持简单：不做敏感字段、表级权限和行级权限；这些长期策略留给 M4。
    """

    if not sql.strip():
        return GuardResult(False, "SQL 为空，无法执行。")

    try:
        parsed_statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.SqlglotError as exc:
        return GuardResult(False, f"SQL Guard 解析失败：{exc}")

    if len(parsed_statements) != 1:
        return GuardResult(False, "只允许单条 SELECT 只读查询。")

    statement = parsed_statements[0]
    if not isinstance(statement, exp.Select):
        return GuardResult(False, "只允许 SELECT 只读查询，禁止 DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE。")

    return GuardResult(True)

