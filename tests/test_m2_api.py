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
    # 测试库直接 create_all 建表即可；Alembic 迁移只守护 MySQL 主路径（M1 约定）。
    Base.metadata.create_all(engine)

    # 灌入 M1 的确定性 seed 数据：下面的断言依赖其中稳定的行数和固定业务事实。
    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        # 测试替身：把正式的 get_db 换成内存库 Session（类比 Spring 测试里的 @MockBean）。
        with Session(engine) as session:
            yield session

    # ★ FastAPI 依赖覆盖机制：接口代码一行不改，测试时底层数据库整体换成 SQLite。
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        # 测试结束必须清理覆盖并删表，避免影响同进程里的其他测试。
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_db_engine_uses_pool_pre_ping_for_stale_mysql_connections() -> None:
    # ★ 守住 M2 关键决策：engine 必须开启 pool_pre_ping，防止拿到被 MySQL 掐断的失效连接。
    # `_pre_ping` 是连接池内部属性，直接读取它确认配置真的生效，而不是只看代码写了参数。
    engine = build_engine("sqlite+pysqlite:///:memory:")

    assert engine.pool._pre_ping is True


def test_products_list_supports_category_status_pagination_and_trace_id() -> None:
    # 守住列表接口三件事：筛选条件生效、分页字段正确、trace_id 在响应头和响应体一致。
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
    # 守住订单接口的组合筛选：支付时间范围（左闭右开）+ 渠道 + 订单状态同时生效。
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
    # 守住退款接口的组合筛选：申请时间范围 + 退款状态 + 退款原因同时生效。
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
    # 守住工单接口的组合筛选：状态 + 优先级 + 工单类型同时生效。
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
    # 守住统一错误契约：非法分页（page=0）必须返回 422 + code/message/trace_id/details
    # 四件套，而不是 FastAPI 默认的裸 {"detail": ...} 结构。
    with _seeded_test_client() as client:
        response = client.get("/api/products", params={"page": 0})

    body = response.json()

    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed."
    assert body["trace_id"] == response.headers["x-trace-id"]
    assert isinstance(body["details"], list)
