"""M5 AgentResponse / Trace / Tool / Chart 测试。

★ M5 的重点不是让 SQL 更聪明，而是把 `/api/query` 的输出整理成评测和演示页能直接消费的
稳定契约：响应体有成本、工具调用、图表 spec；后台有 JSONL trace。
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database


@contextmanager
def _seeded_test_client(trace_path: Path) -> Generator[TestClient, None, None]:
    """创建带 seed 数据和独立 trace 文件的测试客户端。"""

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
    app.state.trace_path = trace_path
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        if hasattr(app.state, "trace_path"):
            delattr(app.state, "trace_path")
        Base.metadata.drop_all(engine)


def test_query_response_contains_m5_contract_and_writes_trace(tmp_path: Path) -> None:
    # 红灯目标：每次查询都要同时满足 API 响应契约和后台 JSONL trace 契约。
    trace_path = tmp_path / "traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops"},
        )

    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sql"
    assert body["docs_used"] == []
    assert body["tables_used"] == ["channels", "orders"]
    assert body["cost"]["latency_ms"] >= 0
    assert body["cost"]["sql_time_ms"] >= 0
    assert body["cost"]["model"] is None
    assert body["cost"]["prompt_tokens"] == 0
    assert body["cost"]["completion_tokens"] == 0
    assert body["tool_calls"][0]["tool_name"] == "sql_query"
    assert body["tool_calls"][0]["status"] == "success"
    assert body["tool_calls"][0]["latency_ms"] >= 0
    assert body["tool_calls"][0]["tables_used"] == ["channels", "orders"]
    assert body["chart_spec"]["mark"] == "bar"
    assert body["chart_spec"]["encoding"]["x"]["field"] == "channel_name"
    assert body["chart_spec"]["encoding"]["y"]["field"] == "order_count"

    trace_lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(trace_lines) == 1
    trace = json.loads(trace_lines[0])
    assert trace["trace_id"] == body["trace_id"]
    assert trace["route"] == "sql"
    assert trace["sql"] == body["sql"]
    assert trace["error_type"] is None
    assert trace["tool_calls"][0]["tool_name"] == "sql_query"
    assert trace["chart_spec"]["mark"] == "bar"


def test_query_blocked_response_keeps_m5_contract_and_trace(tmp_path: Path) -> None:
    # 红灯目标：安全拦截也要有完整字段，EvalOps 才能统一读取 error_type / tool_calls。
    trace_path = tmp_path / "blocked-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "DROP TABLE orders", "user_role": "admin"},
        )

    body = response.json()

    assert response.status_code == 200
    assert body["safety_status"] == "blocked"
    assert body["chart_spec"] is None
    assert body["docs_used"] == []
    assert body["tool_calls"][0]["tool_name"] == "sql_guard"
    assert body["tool_calls"][0]["status"] == "blocked"
    assert body["tool_calls"][0]["error_type"] == "sql_guard_blocked"
    assert body["cost"]["latency_ms"] >= 0

    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert trace["trace_id"] == body["trace_id"]
    assert trace["safety_status"] == "blocked"
    assert trace["error_type"] == "sql_guard_blocked"


def test_aggregation_questions_generate_three_basic_chart_shapes(tmp_path: Path) -> None:
    # 红灯目标：M5 至少覆盖渠道订单量、商品退款率、GMV 三类聚合结果的图表 spec。
    trace_path = tmp_path / "chart-traces.jsonl"

    with _seeded_test_client(trace_path) as client:
        channel_orders = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops"},
        ).json()
        refund_rate = client.post(
            "/api/query",
            json={"question": "2026年6月退款率最高的商品是什么？", "user_role": "ops"},
        ).json()
        june_gmv = client.post(
            "/api/query",
            json={"question": "2026年6月本月GMV是多少？", "user_role": "ops"},
        ).json()

    assert channel_orders["chart_spec"]["mark"] == "bar"
    assert channel_orders["chart_spec"]["encoding"]["x"]["field"] == "channel_name"
    assert channel_orders["chart_spec"]["encoding"]["y"]["field"] == "order_count"

    assert refund_rate["chart_spec"]["mark"] == "bar"
    assert refund_rate["chart_spec"]["encoding"]["y"]["field"] == "product_name"
    assert refund_rate["chart_spec"]["encoding"]["x"]["field"] == "refund_rate"

    assert june_gmv["chart_spec"]["mark"] == "bar"
    assert june_gmv["chart_spec"]["data"]["values"] == [{"metric_name": "gmv", "value": 160247.0}]
