"""M4 RBAC 权限矩阵：定义角色能访问哪些表和字段。

★ 这里先做表级 + 字段级 allowlist，不做行级权限。行级权限通常需要用户身份、数据归属
和更多业务约束，放到后续模块更稳。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RolePolicy:
    """单个角色的表 / 字段访问策略。"""

    allowed_tables: set[str]
    allow_sensitive_fields: bool = False


ALL_TABLES = {
    "users",
    "products",
    "channels",
    "orders",
    "order_items",
    "refunds",
    "tickets",
    "knowledge_docs",
    "product_categories",
    "coupons",
    "order_coupons",
    "user_behavior_log",
    "product_price_history",
    "orders_wide",
}

ROLE_POLICIES: dict[str, RolePolicy] = {
    "admin": RolePolicy(allowed_tables=set(ALL_TABLES), allow_sensitive_fields=True),
    "ops": RolePolicy(allowed_tables=set(ALL_TABLES), allow_sensitive_fields=False),
    "customer_service": RolePolicy(
        allowed_tables={"tickets", "knowledge_docs"},
        allow_sensitive_fields=False,
    ),
    "demo_user": RolePolicy(
        allowed_tables={"products", "channels", "knowledge_docs", "product_categories", "orders_wide"},
        allow_sensitive_fields=False,
    ),
}


def get_role_policy(user_role: str) -> RolePolicy | None:
    """按角色名读取权限策略，未知角色返回 None 并由调用方拦截。"""

    return ROLE_POLICIES.get(user_role)
