from datetime import datetime

from sqlalchemy import ForeignKey, create_engine, inspect
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    Channel,
    Coupon,
    KnowledgeDoc,
    Order,
    OrderCoupon,
    OrderItem,
    OrderWide,
    Product,
    ProductCategory,
    ProductPriceHistory,
    Refund,
    Ticket,
    User,
    UserBehaviorLog,
)
from scripts.seed_data import (
    EXPECTED_SEED_COUNTS,
    REQUIRED_ROLES,
    seed_database,
    verify_business_facts,
)


def test_m1_metadata_contains_all_business_tables() -> None:
    # ★ 这个测试守住数据底座底线：14 张物理表必须全部注册进 Base.metadata。
    # Alembic 后续就是从这个 metadata 里读取表结构并生成 / 校验迁移。
    expected_tables = {
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

    assert expected_tables <= set(Base.metadata.tables)


def test_m1_tables_have_primary_keys_foreign_keys_and_indexes() -> None:
    # 每张表都必须有单列主键 id，方便其他表外键关联，也方便分页和详情查询。
    assert [column.name for column in User.__table__.primary_key] == ["id"]
    assert [column.name for column in Product.__table__.primary_key] == ["id"]
    assert [column.name for column in Channel.__table__.primary_key] == ["id"]
    assert [column.name for column in ProductCategory.__table__.primary_key] == ["id"]
    assert [column.name for column in Order.__table__.primary_key] == ["id"]
    assert [column.name for column in OrderItem.__table__.primary_key] == ["id"]
    assert [column.name for column in Refund.__table__.primary_key] == ["id"]
    assert [column.name for column in Ticket.__table__.primary_key] == ["id"]
    assert [column.name for column in KnowledgeDoc.__table__.primary_key] == ["id"]
    assert [column.name for column in Coupon.__table__.primary_key] == ["id"]
    assert [column.name for column in OrderCoupon.__table__.primary_key] == ["id"]
    assert [column.name for column in UserBehaviorLog.__table__.primary_key] == ["id"]
    assert [column.name for column in ProductPriceHistory.__table__.primary_key] == ["id"]
    assert [column.name for column in OrderWide.__table__.primary_key] == ["id"]

    # 订单、退款、工单是事实表，必须能连回用户、商品、渠道、订单等维表 / 主事实。
    foreign_key_targets = {
        fk.target_fullname
        for table in (
            Product.__table__,
            Order.__table__,
            OrderItem.__table__,
            Refund.__table__,
            Ticket.__table__,
            OrderCoupon.__table__,
            UserBehaviorLog.__table__,
            ProductPriceHistory.__table__,
            OrderWide.__table__,
        )
        for column in table.columns
        for fk in column.foreign_keys
        if isinstance(fk, ForeignKey)
    }

    assert {
        "users.id",
        "products.id",
        "channels.id",
        "orders.id",
        "order_items.id",
        "product_categories.id",
        "coupons.id",
    } <= foreign_key_targets
    # 高频筛选字段必须有索引：后续 API 和 SQL 模板会按角色、状态、优先级过滤。
    assert User.role.property.columns[0].index is True
    assert Order.order_status.property.columns[0].index is True
    assert Refund.refund_status.property.columns[0].index is True
    assert Ticket.priority.property.columns[0].index is True

    order_wide_columns = set(OrderWide.__table__.columns.keys())
    assert {
        "user_role",
        "primary_product_price",
        "item_count",
        "refund_count",
        "total_refund",
        "has_refund",
        "updated_at",
    } <= order_wide_columns


def test_m1_seed_data_counts_roles_and_business_facts_are_stable() -> None:
    # SQLite 只在测试里做快速兜底；阶段二主路径仍然是 MySQL + Alembic。
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # seed_database 是真实 seed 脚本复用的函数，测试直接调用它，避免测一套假逻辑。
        summary = seed_database(session, reset_existing=True)
        counts = summary["counts"]

        # 行数和角色覆盖是 M1 明确验收标准。
        assert counts == EXPECTED_SEED_COUNTS
        assert set(summary["roles"]) == REQUIRED_ROLES

        # 固定业务事实是后续 M3/M6 评测的标准答案锚点。
        facts = verify_business_facts(session)

        assert (
            facts["highest_refund_rate_product_june_2026"]
            == "Aurora Noise Cancelling Headphones"
        )
        assert facts["top_gmv_channel_june_2026"] == "Mobile App"
        assert facts["top_refund_reason"] == "quality_issue"
        assert facts["pending_high_priority_tickets"] == 12
        assert facts["june_fixed_50_top_usage_channel"] == "Mobile App"
        assert facts["top_root_category_by_gmv_june_2026"] == "数码电子"
        assert facts["aurora_avg_price_june_2026"] == 899
        assert facts["top_add_to_pay_device_type"] == "mobile_app"
        assert facts["orders_wide_matches_star_gmv_by_channel"] is True
        assert facts["amount_mismatch_order_count"] == 5

        # ★ snapshot_at 是整批数据的抽取版本（本批为 7 月 1 日），不是 6 月订单的业务时间。
        # 如果误按 snapshot_at 过滤 6 月会得到空集；上面的 paid_at 对账可防止该错误回归。
        wrong_business_month_count = (
            session.query(OrderWide)
            .filter(
                OrderWide.snapshot_at >= datetime(2026, 6, 1),
                OrderWide.snapshot_at < datetime(2026, 7, 1),
            )
            .count()
        )
        assert wrong_business_month_count == 0

        wide_refund_summary = session.query(OrderWide).filter(OrderWide.has_refund.is_(True)).count()
        assert wide_refund_summary > 0

    # 最后从数据库视角再看一次真实建出的表名。EXPECTED_SEED_COUNTS 仍只描述
    # 14 张业务表的 seed 行数；M47 的 task checkpoint/event 是基础设施表，不参与 seed。
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {
        *EXPECTED_SEED_COUNTS,
        "agent_task_checkpoints",
        "agent_task_events",
    }
    coupon_indexes = {index["name"] for index in inspector.get_indexes("coupons")}
    assert "ix_valid_range" in coupon_indexes
