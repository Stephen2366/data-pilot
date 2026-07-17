from sqlalchemy import ForeignKey, create_engine, inspect
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Channel, KnowledgeDoc, Order, Product, Refund, Ticket, User
from scripts.seed_data import (
    EXPECTED_SEED_COUNTS,
    REQUIRED_ROLES,
    seed_database,
    verify_business_facts,
)


def test_m1_metadata_contains_all_business_tables() -> None:
    expected_tables = {
        "users",
        "products",
        "channels",
        "orders",
        "refunds",
        "tickets",
        "knowledge_docs",
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_m1_tables_have_primary_keys_foreign_keys_and_indexes() -> None:
    assert [column.name for column in User.__table__.primary_key] == ["id"]
    assert [column.name for column in Product.__table__.primary_key] == ["id"]
    assert [column.name for column in Channel.__table__.primary_key] == ["id"]
    assert [column.name for column in Order.__table__.primary_key] == ["id"]
    assert [column.name for column in Refund.__table__.primary_key] == ["id"]
    assert [column.name for column in Ticket.__table__.primary_key] == ["id"]
    assert [column.name for column in KnowledgeDoc.__table__.primary_key] == ["id"]

    foreign_key_targets = {
        fk.target_fullname
        for table in (Order.__table__, Refund.__table__, Ticket.__table__)
        for column in table.columns
        for fk in column.foreign_keys
        if isinstance(fk, ForeignKey)
    }

    assert {
        "users.id",
        "products.id",
        "channels.id",
        "orders.id",
    } <= foreign_key_targets
    assert User.role.property.columns[0].index is True
    assert Order.order_status.property.columns[0].index is True
    assert Refund.refund_status.property.columns[0].index is True
    assert Ticket.priority.property.columns[0].index is True


def test_m1_seed_data_counts_roles_and_business_facts_are_stable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        summary = seed_database(session, reset_existing=True)
        counts = summary["counts"]

        assert counts == EXPECTED_SEED_COUNTS
        assert set(summary["roles"]) == REQUIRED_ROLES

        facts = verify_business_facts(session)

        assert facts["highest_refund_rate_product_june_2026"] == "Aurora Noise Cancelling Headphones"
        assert facts["top_gmv_channel_june_2026"] == "Mobile App"
        assert facts["top_refund_reason"] == "quality_issue"
        assert facts["pending_high_priority_tickets"] == 12

    inspector = inspect(engine)
    assert sorted(inspector.get_table_names()) == sorted(EXPECTED_SEED_COUNTS)
