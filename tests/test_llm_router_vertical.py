"""LLM Router 的三路纵向集成：fake Router 模型 + 真实 Harness adapters。"""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.core.config import Settings
from app.main import create_app
from engine.governance import demo_caller
from engine.harness.adapters import RAGToolAdapter, Text2SQLToolAdapter
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest
from engine.harness.graph import HarnessRuntime, run_harness
from engine.harness.llm_router import CompositeIntentRouter
from engine.nl2sql.generator import GeneratedSQL
from scripts.seed_data import seed_database


class _FakeRouterClient:
    """每个纵向场景独享一次 Router usage。"""

    provider_label = "Fake"
    model = "fake-router"

    def __init__(self, response: str) -> None:
        """保存当前场景候选，并初始化独立 usage 计数器。"""

        self.response = response
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    def complete(self, *, prompt: str, system_prompt: str | None = None, node_purpose: str = "") -> str:
        """记录单次假 usage 并返回当前场景的结构化候选。"""

        self.calls += 1
        self.prompt_tokens += 18
        self.completion_tokens += 4
        self.total_tokens += 22
        return self.response


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """真实 SQL adapter 使用隔离 SQLite 和确定性 seed。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)
        yield session
    Base.metadata.drop_all(engine)


def _request(question: str, run_id: str) -> HarnessRequest:
    """构造同时具备 SQL 与客服知识权限的最小纵向请求。"""

    caller = demo_caller(caller_id="llm-router-vertical", roles=("ops", "customer_service"))
    return HarnessRequest(
        question=question,
        run_id=run_id,
        caller=caller,
        active_sql_role="ops",
        force_new_pipeline=False,
    )


@pytest.mark.parametrize(
    ("question", "candidate", "expected_route", "expected_steps"),
    [
        (
            "盘点一下六月成交表现",
            '{"intent":"sql"}',
            "sql",
            ("route", "sql_tool", "controller"),
        ),
        (
            "质量问题退款需要准备哪些材料",
            '{"intent":"rag"}',
            "rag",
            ("route", "rag_tool", "controller"),
        ),
        (
            "六月成交额结果及其计算含义一起给我",
            '{"intent":"hybrid","hybrid_operator":"metric_value_and_definition"}',
            "hybrid",
            ("route", "hybrid_sql_tool", "hybrid_rag_tool", "controller"),
        ),
    ],
)
def test_fake_router_model_drives_real_harness_adapters(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    question: str,
    candidate: str,
    expected_route: str,
    expected_steps: tuple[str, ...],
) -> None:
    """三路均从模型提案进入 compiler，再使用既有 SQL/RAG/Hybrid 深链。"""

    # 开放 SQL 问法故意不命中旧模板；这里只替换 legacy generator，SQL Guard、执行、
    # Evidence、RAG AnswerFlow 与 Harness conditional edge 仍全部是真实实现。
    monkeypatch.setattr(
        "engine.harness.adapters.generate_sql",
        lambda **_kwargs: GeneratedSQL(
            sql=(
                "SELECT ROUND(SUM(order_amount), 2) AS gmv FROM orders "
                "WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' "
                "AND order_status NOT IN ('cancelled', 'canceled')"
            ),
            tables_used=["orders"],
        ),
    )
    client = _FakeRouterClient(candidate)
    runtime = HarnessRuntime(
        sql_tool=Text2SQLToolAdapter(db=db_session),
        rag_tool=RAGToolAdapter(),
        router=CompositeIntentRouter(client_factory=lambda: client),
    )

    result = run_harness(request=_request(question, f"vertical-{expected_route}"), runtime=runtime)

    assert result.route == expected_route
    assert result.graph_steps == expected_steps
    assert result.route_decision.decision_source == "model"
    assert result.route_decision.router_evidence is not None
    assert result.route_decision.router_evidence.total_tokens == 22
    assert client.calls == 1
    if expected_route == "hybrid":
        assert result.hybrid is not None
        assert tuple(branch.branch for branch in result.hybrid.branches) == ("sql", "rag")
    else:
        assert result.observation is not None
        assert result.observation.route == expected_route


def test_three_model_routes_cross_real_api_and_safe_trace(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    tmp_path: Path,
) -> None:
    """同三路再穿过真实 `/api/query` projector，证明 API/Trace 与 Harness 同源。"""

    monkeypatch.setattr(
        "engine.harness.adapters.generate_sql",
        lambda **_kwargs: GeneratedSQL(
            sql=(
                "SELECT ROUND(SUM(order_amount), 2) AS gmv FROM orders "
                "WHERE paid_at >= '2026-06-01' AND paid_at < '2026-07-01' "
                "AND order_status NOT IN ('cancelled', 'canceled')"
            ),
            tables_used=["orders"],
        ),
    )
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            TASK_BOUNDARY_BACKEND="memory",
            HARNESS_ROUTER_MODE="deterministic",
        )
    )
    trace_path = tmp_path / "llm-router-vertical.jsonl"
    application.state.trace_path = trace_path
    application.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    application.state.rag_tool_factory = RAGToolAdapter

    def override_get_db() -> Generator[Session, None, None]:
        """把 API 请求绑定到本用例已填充的隔离数据库会话。"""

        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    cases = (
        ("盘点一下六月成交表现", '{"intent":"sql"}', "sql"),
        ("质量问题退款需要准备哪些材料", '{"intent":"rag"}', "rag"),
        (
            "六月成交额结果及其计算含义一起给我",
            '{"intent":"hybrid","hybrid_operator":"metric_value_and_definition"}',
            "hybrid",
        ),
    )
    try:
        with TestClient(application) as client:
            responses = []
            for question, candidate, expected_route in cases:
                application.state.harness_router = CompositeIntentRouter(
                    client_factory=lambda candidate=candidate: _FakeRouterClient(candidate)
                )
                response = client.post(
                    "/api/query",
                    json={
                        "question": question,
                        "user_role": "ops",
                        "force_new_pipeline": False,
                    },
                )
                assert response.status_code == 200
                assert response.json()["route"] == expected_route
                assert "router_evidence" not in response.json()
                responses.append(response.json())
    finally:
        application.dependency_overrides.clear()

    traces = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [item["route"] for item in traces] == ["sql", "rag", "hybrid"]
    assert all(item["route_decision"]["decision_source"] == "model" for item in traces)
    assert all(item["route_decision"]["router_evidence"]["attempt_count"] == 1 for item in traces)
    assert traces[0]["graph_steps"] == ["route", "sql_tool", "controller"]
    assert traces[1]["graph_steps"] == ["route", "rag_tool", "controller"]
    assert traces[2]["graph_steps"] == ["route", "hybrid_sql_tool", "hybrid_rag_tool", "controller"]
    assert len(traces[2]["hybrid_branches"]) == 2
