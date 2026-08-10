"""M4 NL2SQL 与安全链路测试：schema prompt、LLM SQL 生成、RBAC / 敏感字段拦截。

★ M4 开始从模板 SQL 迈向 LLM 生成 SQL，但测试仍把 LLM 调用替换成假客户端。
这样可以稳定验证“生成结果进入 SQL Guard 和 RBAC”这条主链路，而不是把单测绑到外部网络。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from scripts.seed_data import seed_database


class FakeLLMClient:
    """按问题关键词返回固定 SQL，模拟 DeepSeek 等模型的最小 chat 接口。"""

    def __init__(self, sql_by_keyword: dict[str, str]) -> None:
        self.sql_by_keyword = sql_by_keyword

    def complete(self, *, prompt: str) -> str:
        """返回 JSON 格式的 SQL 生成结果，贴近真实模型的结构化输出。"""

        for keyword, sql in self.sql_by_keyword.items():
            if keyword in prompt:
                return (
                    '{"sql": "'
                    + sql.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
                    + '", "tables_used": [], "confidence": 0.91, "reasoning_summary": "测试假客户端命中"}'
                )
        raise AssertionError(f"测试假客户端没有找到匹配问题：{prompt[-300:]}")


@contextmanager
def _seeded_test_client() -> Generator[TestClient, None, None]:
    """创建带确定性 seed 数据的测试客户端。"""

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


def test_schema_loader_reads_sensitive_fields_and_metrics() -> None:
    # 红灯目标：M4 prompt 和 policy 都要从 domain_pack 读取业务事实，而不是写死在 engine/。
    from engine.nl2sql.schema_loader import load_domain_schema

    domain_schema = load_domain_schema()

    assert "users" in domain_schema.tables
    assert domain_schema.tables["users"].fields["email"].sensitivity == "sensitive"
    assert domain_schema.tables["users"].fields["phone"].sensitivity == "sensitive"
    assert domain_schema.sensitive_fields == {"users.email", "users.phone"}
    assert "gmv" in domain_schema.metrics
    assert "SUM(orders.order_amount)" in domain_schema.metrics["gmv"].formula
    assert domain_schema.examples[0].question


def test_prompt_builder_contains_constraints_schema_metrics_and_few_shot() -> None:
    # 红灯目标：prompt 必须把安全约束、可用表、字段说明、指标口径和 few-shot 放到一起。
    from engine.nl2sql.prompt import build_sql_prompt
    from engine.nl2sql.schema_loader import load_domain_schema

    prompt = build_sql_prompt(
        question="查询 active 商品列表前 10 条",
        user_role="ops",
        domain_schema=load_domain_schema(),
    )

    assert "只生成单条 SELECT" in prompt
    assert "users.email" in prompt
    assert "敏感字段" in prompt
    assert "products" in prompt
    assert "product_name" in prompt
    assert "GMV" in prompt
    assert "few-shot" in prompt


def test_generator_extracts_structured_json_and_fenced_sql() -> None:
    # 红灯目标：真实模型可能返回 JSON，也可能退回 fenced code block，两种都要能提取 SQL。
    from engine.nl2sql.generator import extract_generated_sql

    structured = extract_generated_sql(
        '{"sql": "SELECT product_name FROM products LIMIT 10", '
        '"tables_used": ["products"], "confidence": 0.88, "reasoning_summary": "ok"}'
    )
    fenced = extract_generated_sql(
        "可以执行：\n```sql\nSELECT channel_name FROM channels LIMIT 5\n```"
    )

    assert structured.sql == "SELECT product_name FROM products LIMIT 10"
    assert structured.tables_used == ["products"]
    assert structured.confidence == 0.88
    assert fenced.sql == "SELECT channel_name FROM channels LIMIT 5"
    assert fenced.confidence == 0.5


def test_qwen_chat_client_uses_dashscope_openai_compatible_contract() -> None:
    """Qwen 主模型应复用 OpenAI-compatible 契约，便于和 DeepSeek 做公平 A/B。"""

    from engine.nl2sql.generator import QwenChatClient

    calls: list[dict[str, object]] = []

    def fake_post_json(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return {"choices": [{"message": {"content": '{"sql":"SELECT 1","tables_used":[]}'}}]}

    client = QwenChatClient(
        api_key="dashscope-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3.7-plus",
        post_json=fake_post_json,
    )

    assert client.complete(prompt="生成 SQL", system_prompt="系统约束") == '{"sql":"SELECT 1","tables_used":[]}'
    assert calls[0]["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer dashscope-key"
    assert calls[0]["payload"]["model"] == "qwen3.7-plus"
    assert calls[0]["payload"]["messages"][0] == {"role": "system", "content": "系统约束"}
    assert calls[0]["payload"]["response_format"] == {"type": "json_object"}


def test_get_default_llm_client_can_select_qwen_provider(monkeypatch: Any) -> None:
    """LLM_PROVIDER=qwen 时应显式走 DashScope key，而不是误用 DeepSeek key。"""

    from app.core.config import get_settings
    from engine.nl2sql.generator import QwenChatClient, get_default_llm_client

    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://dashscope.example/compatible-mode/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    get_settings.cache_clear()
    try:
        client = get_default_llm_client()
    finally:
        get_settings.cache_clear()

    assert isinstance(client, QwenChatClient)
    assert client.api_key == "dashscope-key"
    assert client.base_url == "https://dashscope.example/compatible-mode/v1"
    assert client.model == "qwen3.7-plus"


def test_enhanced_guard_blocks_sensitive_fields_and_role_table_access() -> None:
    # 红灯目标：只读 SELECT 还不够，M4 必须拦截敏感字段和越权角色访问。
    from engine.nl2sql.schema_loader import load_domain_schema
    from engine.sql_guard.policy import validate_sql_policy

    domain_schema = load_domain_schema()

    sensitive = validate_sql_policy(
        "SELECT email FROM users LIMIT 10",
        user_role="ops",
        domain_schema=domain_schema,
    )
    admin_sensitive = validate_sql_policy(
        "SELECT email, phone FROM users LIMIT 10",
        user_role="admin",
        domain_schema=domain_schema,
    )
    forbidden_table = validate_sql_policy(
        "SELECT order_no FROM orders LIMIT 10",
        user_role="customer_service",
        domain_schema=domain_schema,
    )
    allowed_ticket = validate_sql_policy(
        "SELECT ticket_no, status FROM tickets WHERE status = 'pending' LIMIT 10",
        user_role="customer_service",
        domain_schema=domain_schema,
    )
    dangerous = validate_sql_policy(
        "DROP TABLE orders",
        user_role="admin",
        domain_schema=domain_schema,
    )

    assert sensitive.is_allowed is False
    assert "敏感字段" in (sensitive.blocked_reason or "")
    assert admin_sensitive.is_allowed is False
    assert "敏感字段" in (admin_sensitive.blocked_reason or "")
    assert forbidden_table.is_allowed is False
    assert "角色 customer_service" in (forbidden_table.blocked_reason or "")
    assert allowed_ticket.is_allowed is True
    assert dangerous.is_allowed is False
    assert "只允许 SELECT" in (dangerous.blocked_reason or "")


def test_query_api_uses_template_first_then_llm_and_applies_policy(monkeypatch: Any) -> None:
    # 红灯目标：模板命中仍走 M3 稳定路径；模板未命中才调用 LLM，且生成 SQL 继续过 policy。
    # M27 v2 起 /api/query 默认走新 Text2SQL 链路；这里显式 force_new_pipeline=False，
    # 验证 legacy 模板优先契约与安全 policy（新默认链路由 test_phase3a_pipeline 覆盖）。
    from engine.nl2sql import generator

    fake_client = FakeLLMClient(
        {
            "查询 active 商品列表前 10 条": (
                "SELECT product_name, category, status FROM products "
                "WHERE status = 'active' ORDER BY product_name ASC LIMIT 10"
            ),
            "查询用户邮箱": "SELECT email FROM users LIMIT 10",
            "查询订单": "SELECT order_no FROM orders LIMIT 10",
        }
    )
    monkeypatch.setattr(generator, "get_default_llm_client", lambda: fake_client)

    with _seeded_test_client() as client:
        llm_allowed = client.post(
            "/api/query",
            json={"question": "查询 active 商品列表前 10 条", "user_role": "ops", "force_new_pipeline": False},
        ).json()
        sensitive_blocked = client.post(
            "/api/query",
            json={"question": "查询用户邮箱", "user_role": "ops", "force_new_pipeline": False},
        ).json()
        role_blocked = client.post(
            "/api/query",
            json={"question": "查询订单", "user_role": "customer_service", "force_new_pipeline": False},
        ).json()
        template_first = client.post(
            "/api/query",
            json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": False},
        ).json()

    assert llm_allowed["safety_status"] == "passed"
    assert llm_allowed["sql"].startswith("SELECT product_name")
    assert llm_allowed["columns"] == ["product_name", "category", "status"]
    assert llm_allowed["rows"]
    assert "active" in str(llm_allowed)

    assert sensitive_blocked["safety_status"] == "blocked"
    assert "敏感字段" in sensitive_blocked["blocked_reason"]
    assert role_blocked["safety_status"] == "blocked"
    assert "角色 customer_service" in role_blocked["blocked_reason"]
    assert template_first["safety_status"] == "passed"
    assert "COUNT(o.id)" in template_first["sql"]
