"""M4 增强 SQL Guard：只读检查 + 表级 RBAC + 敏感字段拦截。

M3 的 `validate_readonly_sql()` 只回答“是不是 SELECT”。M4 在这层继续回答：
这个角色能不能看这些表、这些列。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from engine.nl2sql.schema_loader import DomainSchema
from engine.sql_guard.guard import GuardResult, validate_readonly_sql
from engine.sql_guard.rbac import get_role_policy


@dataclass(frozen=True)
class SQLAccessInfo:
    """从 SQL AST 中提取出的访问对象，便于测试和后续 trace 复用。"""

    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)


def _table_aliases(statement: exp.Expression) -> dict[str, str]:
    """收集 SQL 中 `orders o` 这种 alias 到真实表名的映射。"""

    aliases: dict[str, str] = {}
    for table in statement.find_all(exp.Table):
        table_name = table.name
        aliases[table_name] = table_name
        if table.alias:
            aliases[table.alias] = table_name
    return aliases


def _qualify_column(column: exp.Column, aliases: dict[str, str], domain_schema: DomainSchema) -> set[str]:
    """把 AST Column 尽量转换成 `table.column`。

    未写表名前缀且只有一个候选表时直接补齐；多表同名字段保持多个候选，让 policy 偏保守。
    """

    column_name = column.name
    table_prefix = column.table
    if table_prefix:
        return {f"{aliases.get(table_prefix, table_prefix)}.{column_name}"}

    candidates = {
        f"{table_name}.{column_name}"
        for table_name in aliases.values()
        if table_name in domain_schema.tables and column_name in domain_schema.tables[table_name].fields
    }
    return candidates


def extract_sql_access(sql: str, domain_schema: DomainSchema) -> SQLAccessInfo:
    """使用 sqlglot AST 提取 SQL 访问的表和列。"""

    statement = sqlglot.parse_one(sql, read="mysql")
    aliases = _table_aliases(statement)
    tables = set(aliases.values())
    columns: set[str] = set()

    # 步骤 1：提取显式列引用 --------------------------------------------------------------
    for column in statement.find_all(exp.Column):
        columns.update(_qualify_column(column, aliases, domain_schema))

    # 步骤 2：处理 SELECT * ----------------------------------------------------------------
    # ★ 对非 admin 来说，`SELECT * FROM users` 会把 email/phone 一起带出，所以必须展开后检查。
    for star in statement.find_all(exp.Star):
        parent = star.parent
        table_prefix = getattr(parent, "table", None)
        target_tables = {aliases.get(table_prefix, table_prefix)} if table_prefix else tables
        for table_name in target_tables:
            table = domain_schema.tables.get(table_name)
            if table:
                columns.update(f"{table_name}.{field_name}" for field_name in table.fields)

    return SQLAccessInfo(tables=tables, columns=columns)


def validate_sql_policy(sql: str, *, user_role: str, domain_schema: DomainSchema) -> GuardResult:
    """执行 M4 完整 SQL 安全策略。"""

    readonly_result = validate_readonly_sql(sql)
    if not readonly_result.is_allowed:
        return readonly_result

    role_policy = get_role_policy(user_role)
    if role_policy is None:
        return GuardResult(False, f"未知角色 {user_role}，无法执行查询。")

    try:
        access = extract_sql_access(sql, domain_schema)
    except sqlglot.errors.SqlglotError as exc:
        return GuardResult(False, f"SQL Guard 解析失败：{exc}")

    forbidden_tables = sorted(access.tables - role_policy.allowed_tables)
    if forbidden_tables:
        return GuardResult(False, f"角色 {user_role} 不允许访问表：{', '.join(forbidden_tables)}。")

    sensitive_columns = sorted(access.columns & domain_schema.sensitive_fields)
    if sensitive_columns and not role_policy.allow_sensitive_fields:
        return GuardResult(False, f"命中敏感字段：{', '.join(sensitive_columns)}；角色 {user_role} 不允许访问。")

    return GuardResult(True)
