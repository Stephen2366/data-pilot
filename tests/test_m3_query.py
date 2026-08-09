"""M3 v0 查询闭环测试：模板匹配、SQL Guard、/api/query 结构化响应。

★ 这些测试先定义 DataPilot v0 的行为契约：自然语言只能命中预设模板，
SQL 必须先经过只读安全检查，接口必须返回 AgentResponse，而不是散装 dict。
"""

from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database


@contextmanager
def _seeded_test_client() -> Generator[TestClient, None, None]:
    """创建带 M1 确定性 seed 数据的测试客户端。

    ★ SQLite 只用于自动化测试；M3 主链路仍通过 app.db.session 的正式入口连接 MySQL。
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


def test_template_match_returns_sql_route_and_parameters_for_refund_rate() -> None:
    # 红灯目标：自然语言“退款率最高商品”要稳定命中模板，而不是交给 LLM 自由发挥。
    from engine.nl2sql.templates import match_template

    matched = match_template("2026年6月退款率最高的商品是什么？")

    assert matched is not None
    assert matched.template_id == "highest_refund_rate_product_june_2026"
    assert matched.route == "sql"
    assert "refund_rate" in matched.sql
    assert matched.parameters == {
        "month_start": "2026-06-01 00:00:00",
        "month_end": "2026-07-01 00:00:00",
    }


def test_sql_guard_allows_select_and_blocks_dangerous_writes() -> None:
    # 红灯目标：M3 的安全底线是 sqlglot AST 只读检查，危险 DDL / DML 不能进数据库。
    from engine.sql_guard.guard import validate_readonly_sql

    allowed = validate_readonly_sql("SELECT channel_name FROM channels LIMIT 5")
    assert allowed.is_allowed is True
    assert allowed.blocked_reason is None

    for dangerous_sql in [
        "DROP TABLE orders",
        "DELETE FROM refunds WHERE id = 1",
        "UPDATE tickets SET status = 'closed'",
        "INSERT INTO channels (channel_name) VALUES ('x')",
        "ALTER TABLE users ADD COLUMN secret_token VARCHAR(255)",
        "TRUNCATE TABLE products",
    ]:
        blocked = validate_readonly_sql(dangerous_sql)
        assert blocked.is_allowed is False, dangerous_sql
        assert blocked.blocked_reason is not None


def test_query_api_returns_agent_response_for_five_template_questions() -> None:
    # 红灯目标：5 个高价值问题都要返回简化版 AgentResponse，并带可消费的表格数据。
    # M27 v2 起 /api/query 默认走新 Text2SQL 链路；这里显式 force_new_pipeline=False，
    # 继续验证 legacy 模板契约（与 runbook 的显式回退入口一致）。
    questions_and_expected = [
        ("2026年6月退款率最高的商品是什么？", "Aurora Noise Cancelling Headphones"),
        ("各渠道订单量是多少？", "Mobile App"),
        ("2026年6月本月GMV是多少？", "gmv"),
        ("Top退款原因是什么？", "quality_issue"),
        ("待处理高优先级工单有多少？", "12"),
    ]

    with _seeded_test_client() as client:
        for question, expected_text in questions_and_expected:
            response = client.post(
                "/api/query",
                json={"question": question, "user_role": "ops", "force_new_pipeline": False},
            )

            body = response.json()

            assert response.status_code == 200
            assert body["route"] == "sql"
            assert body["safety_status"] == "passed"
            assert body["blocked_reason"] is None
            assert body["trace_id"] == response.headers["x-trace-id"]
            assert body["sql"].lower().startswith("select")
            assert body["columns"]
            assert body["rows"]
            assert expected_text in str(body)


def test_query_api_blocks_dangerous_sql_with_structured_agent_response() -> None:
    # 红灯目标：即使用户直接输入危险 SQL，接口也只能返回结构化拦截结果，不能执行。
    with _seeded_test_client() as client:
        response = client.post(
            "/api/query",
            json={"question": "DROP TABLE orders", "user_role": "admin"},
        )

    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sql"
    assert body["answer"] == "SQL Guard 已拦截该请求。"
    assert body["safety_status"] == "blocked"
    assert "只允许 SELECT" in body["blocked_reason"]
    assert body["columns"] == []
    assert body["rows"] == []
