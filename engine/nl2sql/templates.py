"""M3 模板 SQL：把少量高价值自然语言问题映射成稳定 SQL。

★ v0 暂不引入 LLM，自然语言只在这里命中白名单模板。这样后续接 LLM 前，
已经有一条可验证、可复用、可安全拦截的 SQL 主链路。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SQLTemplate:
    """一个模板问题的完整定义。

    字段说明：
    - template_id：评测和 few-shot 示例复用的稳定 ID。
    - question_keywords：最小关键词集合，全部命中才算匹配。
    - sql：参数化 SQL，进入数据库前仍必须经过 SQL Guard。
    - parameters：固定时间窗口等模板参数，避免把日期硬编码散在路由里。
    """

    template_id: str
    question_keywords: tuple[str, ...]
    sql: str
    parameters: dict[str, str]
    answer_hint: str
    route: str = "sql"


@dataclass(frozen=True)
class MatchedTemplate:
    """模板匹配结果：给 `/api/query` 提供 route、SQL、参数和回答提示。"""

    template_id: str
    route: str
    sql: str
    parameters: dict[str, str]
    answer_hint: str


JUNE_2026_PARAMETERS = {
    "month_start": "2026-06-01 00:00:00",
    "month_end": "2026-07-01 00:00:00",
}

# 步骤 1：定义 v0 白名单模板 ==================================================================
# ★ 这里的 SQL 必须同时兼容 MySQL 主路径和 SQLite 测试路径，所以只使用基础 SELECT / JOIN /
# GROUP BY / ORDER BY / LIMIT 语法，不使用方言专属函数。
TEMPLATES: tuple[SQLTemplate, ...] = (
    SQLTemplate(
        template_id="highest_refund_rate_product_june_2026",
        question_keywords=("退款率", "最高", "商品"),
        sql="""
SELECT
  p.product_name,
  COUNT(DISTINCT r.id) AS refund_count,
  COUNT(DISTINCT o.id) AS order_count,
  ROUND(COUNT(DISTINCT r.id) * 1.0 / COUNT(DISTINCT o.id), 4) AS refund_rate
FROM products p
JOIN orders o ON o.product_id = p.id
LEFT JOIN refunds r ON r.order_id = o.id
WHERE o.paid_at >= :month_start AND o.paid_at < :month_end
GROUP BY p.id, p.product_name
ORDER BY refund_rate DESC, p.product_name ASC
LIMIT 5
""".strip(),
        parameters=JUNE_2026_PARAMETERS,
        answer_hint="2026-06 退款率最高商品",
    ),
    SQLTemplate(
        template_id="channel_order_count",
        question_keywords=("渠道", "订单量"),
        sql="""
SELECT
  c.channel_name,
  COUNT(o.id) AS order_count
FROM channels c
JOIN orders o ON o.channel_id = c.id
GROUP BY c.id, c.channel_name
ORDER BY order_count DESC, c.channel_name ASC
""".strip(),
        parameters={},
        answer_hint="各渠道订单量",
    ),
    SQLTemplate(
        template_id="gmv_june_2026",
        question_keywords=("gmv",),
        sql="""
SELECT
  ROUND(SUM(o.order_amount), 2) AS gmv
FROM orders o
WHERE o.paid_at >= :month_start
  AND o.paid_at < :month_end
  AND o.order_status NOT IN ('cancelled', 'canceled')
""".strip(),
        parameters=JUNE_2026_PARAMETERS,
        answer_hint="2026-06 GMV",
    ),
    SQLTemplate(
        template_id="top_refund_reason",
        question_keywords=("退款", "原因"),
        sql="""
SELECT
  r.refund_reason,
  COUNT(r.id) AS refund_count
FROM refunds r
GROUP BY r.refund_reason
ORDER BY refund_count DESC, r.refund_reason ASC
LIMIT 5
""".strip(),
        parameters={},
        answer_hint="Top 退款原因",
    ),
    SQLTemplate(
        template_id="pending_high_priority_tickets",
        question_keywords=("待处理", "高优先级", "工单"),
        sql="""
SELECT
  COUNT(t.id) AS pending_high_priority_tickets
FROM tickets t
WHERE t.status = 'pending' AND t.priority = 'high'
""".strip(),
        parameters={},
        answer_hint="待处理高优先级工单数量",
    ),
)


def _normalize_question(question: str) -> str:
    """把问题规范化后再做关键词匹配，避免大小写和空格影响模板命中。"""

    return question.lower().replace(" ", "")


def match_template(question: str) -> MatchedTemplate | None:
    """按关键词匹配 v0 模板 SQL。

    ★ 这是 M3 的“自然语言 → SQL”最小实现。没命中就返回 None，不偷偷调用 LLM，
    防止 v0 范围膨胀。
    """

    normalized = _normalize_question(question)
    for template in TEMPLATES:
        if all(keyword.lower() in normalized for keyword in template.question_keywords):
            return MatchedTemplate(
                template_id=template.template_id,
                route=template.route,
                sql=template.sql,
                parameters=dict(template.parameters),
                answer_hint=template.answer_hint,
            )
    return None
