"""M4 RBAC 权限矩阵：定义角色能访问哪些表和字段。

★ 这里先做表级 + 字段级 allowlist，不做行级权限。行级权限通常需要用户身份、数据归属
和更多业务约束，放到后续模块更稳。
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.nl2sql.schema_loader import DEFAULT_QUERYABLE_TABLE_NAMES


@dataclass(frozen=True)
class RolePolicy:
    """单个角色的表 / 字段访问策略。"""

    allowed_tables: set[str]
    allow_sensitive_fields: bool = False


# 历史名称保留给现有调用者，但语义已明确为“全部可查询分析表”，不是全部物理表。
# 集合从默认 Domain Schema 文件发现结果派生，避免 admin/ops 与 prompt 各维护一份表名单。
ALL_TABLES = set(DEFAULT_QUERYABLE_TABLE_NAMES)

ROLE_POLICIES: dict[str, RolePolicy] = {
    "admin": RolePolicy(allowed_tables=set(ALL_TABLES), allow_sensitive_fields=False),
    "ops": RolePolicy(allowed_tables=set(ALL_TABLES), allow_sensitive_fields=False),
    "customer_service": RolePolicy(
        allowed_tables={"tickets"},
        allow_sensitive_fields=False,
    ),
    "demo_user": RolePolicy(
        allowed_tables={"products", "channels", "product_categories", "orders_wide"},
        allow_sensitive_fields=False,
    ),
}


def get_role_policy(user_role: str) -> RolePolicy | None:
    """按角色名读取权限策略，未知角色返回 None 并由调用方拦截。"""

    return ROLE_POLICIES.get(user_role)
