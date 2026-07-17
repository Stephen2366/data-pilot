from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.models import Channel, KnowledgeDoc, Order, Product, Refund, Ticket, User


EXPECTED_SEED_COUNTS = {
    "users": 50,
    "products": 30,
    "channels": 6,
    "orders": 500,
    "refunds": 80,
    "tickets": 120,
    "knowledge_docs": 8,
}
REQUIRED_ROLES = {"admin", "ops", "customer_service", "demo_user"}


# 固定事实说明 ================================================================
# ★ 这些事实是后续 SQL 评测的“标准答案锚点”，seed 每次重跑都保持稳定：
# 1. 2026-06 退款率最高商品：Aurora Noise Cancelling Headphones。
# 2. 2026-06 GMV 最高渠道：Mobile App。
# 3. 全量退款 Top 原因：quality_issue。
# 4. 待处理高优先级工单数量：12。


def seed_database(session: Session, reset_existing: bool = False) -> dict[str, Any]:
    """Seed deterministic demo data into an already-migrated database.

    参数说明：
    - session：外部传入事务会话，方便 API、测试和命令行复用同一套逻辑。
    - reset_existing：为 True 时先清空 7 张业务表；生产环境不要对真实库使用。
    """

    if reset_existing:
        _delete_existing_rows(session)

    users = _build_users()
    products = _build_products()
    channels = _build_channels()
    docs = _build_knowledge_docs()

    session.add_all([*users, *products, *channels, *docs])
    session.flush()

    orders = _build_orders(users=users, products=products, channels=channels)
    session.add_all(orders)
    session.flush()

    refunds = _build_refunds(orders)
    tickets = _build_tickets(users=users, orders=orders)
    session.add_all([*refunds, *tickets])
    session.commit()

    counts = _count_seed_tables(session)
    return {
        "counts": counts,
        "roles": sorted({user.role for user in users}),
        "facts": verify_business_facts(session),
    }


def verify_business_facts(session: Session) -> dict[str, Any]:
    """Run stable SQL-style checks for the business facts embedded in seed data."""

    june_start = datetime(2026, 6, 1)
    july_start = datetime(2026, 7, 1)

    # 事实 1：按商品统计 2026-06 退款率，退款率 = 退款订单数 / 订单数。
    refund_rate_stmt = (
        select(
            Product.product_name,
            (
                func.count(func.distinct(Refund.id))
                * 1.0
                / func.count(func.distinct(Order.id))
            ).label("refund_rate"),
        )
        .join(Order, Order.product_id == Product.id)
        .outerjoin(Refund, Refund.order_id == Order.id)
        .where(Order.paid_at >= june_start, Order.paid_at < july_start)
        .group_by(Product.id, Product.product_name)
        .order_by(
            (
                func.count(func.distinct(Refund.id))
                * 1.0
                / func.count(func.distinct(Order.id))
            ).desc(),
            Product.product_name.asc(),
        )
        .limit(1)
    )
    highest_refund_rate_product = session.execute(refund_rate_stmt).scalar_one()

    # 事实 2：按渠道统计 2026-06 GMV，排除已取消订单。
    gmv_stmt = (
        select(Channel.channel_name, func.sum(Order.order_amount).label("gmv"))
        .join(Order, Order.channel_id == Channel.id)
        .where(
            Order.paid_at >= june_start,
            Order.paid_at < july_start,
            Order.order_status != "cancelled",
        )
        .group_by(Channel.id, Channel.channel_name)
        .order_by(func.sum(Order.order_amount).desc(), Channel.channel_name.asc())
        .limit(1)
    )
    top_gmv_channel = session.execute(gmv_stmt).scalar_one()

    # 事实 3：全量退款原因 Top 1。
    reason_stmt = (
        select(Refund.refund_reason, func.count(Refund.id).label("refund_count"))
        .group_by(Refund.refund_reason)
        .order_by(func.count(Refund.id).desc(), Refund.refund_reason.asc())
        .limit(1)
    )
    top_refund_reason = session.execute(reason_stmt).scalar_one()

    # 事实 4：待处理高优先级工单数量。
    pending_ticket_stmt = select(func.count(Ticket.id)).where(
        Ticket.status == "pending", Ticket.priority == "high"
    )
    pending_high_priority_tickets = session.execute(pending_ticket_stmt).scalar_one()

    return {
        "highest_refund_rate_product_june_2026": highest_refund_rate_product,
        "top_gmv_channel_june_2026": top_gmv_channel,
        "top_refund_reason": top_refund_reason,
        "pending_high_priority_tickets": pending_high_priority_tickets,
    }


def _delete_existing_rows(session: Session) -> None:
    # 按外键依赖从子表到父表删除，避免 MySQL 外键约束阻止清空。
    for model in (Ticket, Refund, Order, KnowledgeDoc, Product, Channel, User):
        session.execute(delete(model))
    session.flush()


def _build_users() -> list[User]:
    users: list[User] = []
    roles = ["admin", "ops", "customer_service", "demo_user"]

    for index in range(EXPECTED_SEED_COUNTS["users"]):
        role = roles[index % len(roles)]
        users.append(
            User(
                user_name=f"Demo User {index + 1:02d}",
                role=role,
                email=f"user{index + 1:02d}@datapilot.example",
                phone=f"1380000{index + 1:04d}",
                status="active" if index < 46 else "disabled",
            )
        )

    return users


def _build_products() -> list[Product]:
    products = [
        Product(
            sku="SKU-HIGH-REFUND-01",
            product_name="Aurora Noise Cancelling Headphones",
            category="Electronics",
            status="active",
            price=Decimal("899.00"),
            launched_at=datetime(2026, 1, 10),
        )
    ]
    categories = ["Electronics", "Home", "Beauty", "SaaS", "Outdoor"]

    for index in range(1, EXPECTED_SEED_COUNTS["products"]):
        products.append(
            Product(
                sku=f"SKU-{index + 1:04d}",
                product_name=f"DataPilot Demo Product {index + 1:02d}",
                category=categories[index % len(categories)],
                status="active" if index % 11 else "paused",
                price=Decimal(79 + index * 13).quantize(Decimal("0.01")),
                launched_at=datetime(2026, 1, 1) + timedelta(days=index * 3),
            )
        )

    return products


def _build_channels() -> list[Channel]:
    return [
        Channel(channel_code="mobile_app", channel_name="Mobile App", channel_type="owned"),
        Channel(channel_code="web_store", channel_name="Web Store", channel_type="owned"),
        Channel(channel_code="tmall", channel_name="Tmall", channel_type="marketplace"),
        Channel(channel_code="jd", channel_name="JD", channel_type="marketplace"),
        Channel(channel_code="douyin", channel_name="Douyin", channel_type="paid"),
        Channel(channel_code="partner", channel_name="Partner", channel_type="partner"),
    ]


def _build_orders(
    users: list[User], products: list[Product], channels: list[Channel]
) -> list[Order]:
    orders: list[Order] = []
    june_start = datetime(2026, 6, 1, 9, 0, 0)
    may_start = datetime(2026, 5, 1, 9, 0, 0)
    statuses = ["paid", "shipped", "delivered", "cancelled"]

    for index in range(EXPECTED_SEED_COUNTS["orders"]):
        if index < 40:
            product = products[0]
        else:
            product = products[(index % (len(products) - 1)) + 1]

        if index < 170:
            channel = channels[0]
            amount = Decimal("899.00") + Decimal(index % 5) * Decimal("50.00")
        else:
            channel = channels[(index % (len(channels) - 1)) + 1]
            amount = Decimal("109.00") + Decimal(index % 17) * Decimal("23.00")

        paid_at = (june_start if index < 320 else may_start) + timedelta(
            days=index % 28, hours=index % 7
        )
        status = statuses[index % len(statuses)]

        orders.append(
            Order(
                order_no=f"ORD-2026-{index + 1:05d}",
                user=users[index % len(users)],
                product=product,
                channel=channel,
                order_status=status,
                order_amount=amount,
                quantity=1 + (index % 3),
                paid_at=paid_at,
            )
        )

    return orders


def _build_refunds(orders: list[Order]) -> list[Refund]:
    refunds: list[Refund] = []
    reasons = (
        ["quality_issue"] * 42
        + ["late_delivery"] * 15
        + ["wrong_item"] * 12
        + ["changed_mind"] * 11
    )
    statuses = ["approved", "completed", "requested", "rejected"]

    # 先集中给锚点商品生成 18 条退款，确保它在 2026-06 的退款率最高。
    refund_order_indexes = list(range(18))
    refund_order_indexes.extend(range(60, 60 + EXPECTED_SEED_COUNTS["refunds"] - 18))

    for index, order_index in enumerate(refund_order_indexes):
        order = orders[order_index]
        requested_at = order.paid_at + timedelta(days=2 + index % 5)
        processed_at = requested_at + timedelta(days=1) if index % 4 != 2 else None
        refunds.append(
            Refund(
                refund_no=f"REF-2026-{index + 1:05d}",
                order=order,
                user=order.user,
                product=order.product,
                refund_status=statuses[index % len(statuses)],
                refund_reason=reasons[index],
                refund_amount=(order.order_amount * Decimal("0.90")).quantize(
                    Decimal("0.01")
                ),
                requested_at=requested_at,
                processed_at=processed_at,
            )
        )

    return refunds


def _build_tickets(users: list[User], orders: list[Order]) -> list[Ticket]:
    tickets: list[Ticket] = []
    ticket_types = ["refund", "shipping", "invoice", "account", "product"]
    service_users = [user for user in users if user.role == "customer_service"]

    for index in range(EXPECTED_SEED_COUNTS["tickets"]):
        is_anchor_ticket = index < 12
        priority = "high" if is_anchor_ticket else ["low", "medium", "urgent"][index % 3]
        status = "pending" if is_anchor_ticket else ["processing", "resolved", "closed"][index % 3]
        created_at = datetime(2026, 6, 1, 10, 0, 0) + timedelta(hours=index * 3)
        resolved_at = None if status in {"pending", "processing"} else created_at + timedelta(days=2)

        tickets.append(
            Ticket(
                ticket_no=f"TCK-2026-{index + 1:05d}",
                user=users[index % len(users)],
                order=orders[index % len(orders)] if index % 5 != 0 else None,
                assigned_user=service_users[index % len(service_users)],
                ticket_type=ticket_types[index % len(ticket_types)],
                priority=priority,
                status=status,
                subject=f"Demo support ticket {index + 1:03d}",
                description="用于 DataPilot M1 seed 的客服工单样例。",
                resolved_at=resolved_at,
                created_at=created_at,
            )
        )

    return tickets


def _build_knowledge_docs() -> list[KnowledgeDoc]:
    docs = [
        ("refund_policy_basic", "基础退款政策", "refund_policy", "customer_service"),
        ("refund_policy_quality", "质量问题退款规则", "refund_policy", "customer_service"),
        ("shipping_delay_rule", "物流延迟处理规则", "support_rule", "customer_service"),
        ("invoice_rule", "发票开具规则", "support_rule", "customer_service"),
        ("vip_service_rule", "高价值客户服务规则", "support_rule", "ops"),
        ("sensitive_data_policy", "敏感字段访问规范", "security_policy", "admin"),
        ("demo_user_scope", "演示账号数据范围", "security_policy", "demo_user"),
        ("gmv_metric_note", "GMV 指标口径说明", "metric_definition", "ops"),
    ]
    return [
        KnowledgeDoc(
            doc_key=doc_key,
            title=title,
            doc_type=doc_type,
            audience_role=audience_role,
            status="active",
            content=f"{title}：这是阶段二 M1 的知识库草稿，后续 RAG 模块会继续扩展。",
        )
        for doc_key, title, doc_type, audience_role in docs
    ]


def _count_seed_tables(session: Session) -> dict[str, int]:
    models = {
        "users": User,
        "products": Product,
        "channels": Channel,
        "orders": Order,
        "refunds": Refund,
        "tickets": Ticket,
        "knowledge_docs": KnowledgeDoc,
    }
    return {
        table_name: session.execute(select(func.count(model.id))).scalar_one()
        for table_name, model in models.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed DataPilot M1 demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing M1 business rows before seeding.",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)

    # 命令行脚本只负责写数据，不调用 create_all；建表主路径必须走 Alembic。
    with SessionLocal() as session:
        summary = seed_database(session, reset_existing=args.reset)

    print("Seed completed.")
    print(summary)


if __name__ == "__main__":
    main()
