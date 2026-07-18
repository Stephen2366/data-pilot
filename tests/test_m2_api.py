from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import build_engine, get_db
from app.main import app
from scripts.seed_data import seed_database


@contextmanager
def _seeded_test_client() -> Generator[TestClient, None, None]:
    """Create an API client backed by the real M1 seed data in SQLite.

    ★ 这里用 SQLite 只服务自动化测试；应用主路径仍然是 MySQL。StaticPool 让
    所有请求复用同一个内存库连接，否则每次 Session 都会看到一座空数据库。
    """

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_db_engine_uses_pool_pre_ping_for_stale_mysql_connections() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")

    assert engine.pool._pre_ping is True


def test_products_list_supports_category_status_pagination_and_trace_id() -> None:
    with _seeded_test_client() as client:
        response = client.get(
            "/api/products",
            params={
                "category": "Electronics",
                "status": "active",
                "page": 1,
                "page_size": 5,
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert response.headers["x-trace-id"] == body["trace_id"]
    assert body["page"] == 1
    assert body["page_size"] == 5
    assert body["total"] >= 1
    assert 1 <= len(body["items"]) <= 5
    assert {item["category"] for item in body["items"]} == {"Electronics"}
    assert {item["status"] for item in body["items"]} == {"active"}


def test_orders_list_supports_time_channel_status_filters() -> None:
    with _seeded_test_client() as client:
        response = client.get(
            "/api/orders",
            params={
                "paid_from": "2026-06-01T00:00:00",
                "paid_to": "2026-07-01T00:00:00",
                "channel_id": 1,
                "order_status": "paid",
                "page_size": 10,
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert body["total"] >= 1
    assert 1 <= len(body["items"]) <= 10
    for item in body["items"]:
        assert item["channel_id"] == 1
        assert item["order_status"] == "paid"
        assert datetime.fromisoformat(item["paid_at"]) >= datetime(2026, 6, 1)
        assert datetime.fromisoformat(item["paid_at"]) < datetime(2026, 7, 1)


def test_refunds_list_supports_time_status_reason_filters() -> None:
    with _seeded_test_client() as client:
        response = client.get(
            "/api/refunds",
            params={
                "requested_from": "2026-06-01T00:00:00",
                "requested_to": "2026-07-01T00:00:00",
                "refund_status": "approved",
                "refund_reason": "quality_issue",
                "page_size": 10,
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert body["total"] >= 1
    assert 1 <= len(body["items"]) <= 10
    for item in body["items"]:
        assert item["refund_status"] == "approved"
        assert item["refund_reason"] == "quality_issue"
        assert datetime.fromisoformat(item["requested_at"]) >= datetime(2026, 6, 1)
        assert datetime.fromisoformat(item["requested_at"]) < datetime(2026, 7, 1)


def test_tickets_list_supports_status_priority_type_filters() -> None:
    with _seeded_test_client() as client:
        response = client.get(
            "/api/tickets",
            params={
                "status": "pending",
                "priority": "high",
                "ticket_type": "refund",
                "page_size": 10,
            },
        )

    body = response.json()

    assert response.status_code == 200
    assert body["total"] >= 1
    assert 1 <= len(body["items"]) <= 10
    for item in body["items"]:
        assert item["status"] == "pending"
        assert item["priority"] == "high"
        assert item["ticket_type"] == "refund"


def test_invalid_pagination_returns_unified_error_response() -> None:
    with _seeded_test_client() as client:
        response = client.get("/api/products", params={"page": 0})

    body = response.json()

    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed."
    assert body["trace_id"] == response.headers["x-trace-id"]
    assert isinstance(body["details"], list)
