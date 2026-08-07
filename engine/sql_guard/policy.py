"""M4 增强 SQL Guard：只读检查 + 表级 RBAC + 敏感字段拦截。

M3 的 `validate_readonly_sql()` 只回答“是不是 SELECT”。M4 在这层继续回答：
这个角色能不能看这些表、这些列。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, build_scope

from engine.nl2sql.schema_loader import DomainSchema
from engine.sql_guard.guard import GuardResult, validate_readonly_sql
from engine.sql_guard.rbac import get_role_policy


@dataclass(frozen=True)
class SQLAccessInfo:
    """从 SQL AST 中提取出的访问对象，便于测试和后续 trace 复用。"""

    tables: set[str] = field(default_factory=set)
    columns: set[str] = field(default_factory=set)


def _scope_physical_sources(scope: Scope) -> tuple[dict[str, str], set[str]]:
    """提取单个 AST scope 的真实物理表，刻意不把 CTE / derived alias 当成表。

    例如 ``WITH category_tree AS (...) SELECT * FROM category_tree`` 的外层 source 在
    sqlglot 看来是 Scope，不是 ``exp.Table``；真正应做 RBAC 的是 CTE 内部的
    ``product_categories``。按 scope 处理也避免嵌套查询里同名 alias 相互污染。
    """

    aliases: dict[str, str] = {}
    physical_tables: set[str] = set()
    for alias, (_, source) in scope.selected_sources.items():
        if not isinstance(source, exp.Table):
            continue
        table_name = source.name
        aliases[alias] = table_name
        aliases[table_name] = table_name
        physical_tables.add(table_name)
    return aliases, physical_tables


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
    """使用 sqlglot AST 提取真实物理表和字段访问。

    ★ CTE 名是查询内部临时结果，不是数据权限对象：不能因它不在 RBAC allowlist 被误拦；
    但每个 CTE scope 内读到的物理表和敏感字段仍必须加入同一份访问集合并严格检查。
    """

    statement = sqlglot.parse_one(sql, read="mysql")
    root_scope = build_scope(statement)
    if root_scope is None:
        raise sqlglot.errors.SqlglotError("SQL Guard 无法建立 scope")

    tables: set[str] = set()
    columns: set[str] = set()

    # 步骤 1：逐 scope 收集显式字段；scope.columns 不会把 CTE 子查询字段混到外层 ----------
    for scope in root_scope.traverse():
        aliases, scope_tables = _scope_physical_sources(scope)
        tables.update(scope_tables)
        for column in scope.columns:
            columns.update(_qualify_column(column, aliases, domain_schema))

        # 步骤 2：在同一 scope 展开 SELECT * ----------------------------------------------
        # 外层 ``SELECT * FROM cte`` 没有物理表可展开；CTE 内的 ``SELECT * FROM users``
        # 则在它自己的 scope 展开 users.email/users.phone，敏感策略不会被绕过。
        for star in scope.expression.find_all(exp.Star):
            parent = star.parent
            table_prefix = getattr(parent, "table", None)
            target_tables = {aliases.get(table_prefix, table_prefix)} if table_prefix else scope_tables
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
