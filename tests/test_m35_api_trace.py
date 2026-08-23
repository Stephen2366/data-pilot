"""M35 API caller seam、四轴兼容投影与 Graph Trace 回归。"""

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
from engine.harness.caller import FixtureCallerResolver
from engine.harness.adapters import RAGToolAdapter
from scripts.seed_data import seed_database


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    """创建隔离 SQLite / trace / fixture resolver，避免测试污染默认运行证据。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        """让本次 TestClient 请求取得隔离 SQLite Session。"""

        with Session(engine) as session:
            yield session

    previous_resolver = getattr(app.state, "caller_resolver", None)
    previous_rag_factory = getattr(app.state, "rag_tool_factory", None)
    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    # M44A 后普通产品请求不再隐式使用业务小语料；历史合同测试必须显式注入 fixture。
    app.state.rag_tool_factory = lambda: RAGToolAdapter()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver = previous_resolver
        app.state.rag_tool_factory = previous_rag_factory
        Base.metadata.drop_all(engine)


def test_sql_response_and_trace_are_projections_of_one_graph_run(tmp_path: Path) -> None:
    """旧 SQL 字段与新四轴/Trace 必须指向同一次 route → sql_tool → controller。"""

    trace_path = tmp_path / "m35-sql.jsonl"
    with _client(trace_path) as client:
        response = client.post(
            "/api/query", json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": False}
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert (body["route"], body["execution_status"], body["answer_status"], body["safety_status"]) == (
        "sql", "completed", "complete", "passed"
    )
    assert body["docs_used"] == []
    assert body["blocked_reason"] is None
    assert trace["trace_id"] == body["trace_id"]
    assert trace["route"] == body["route"]
    assert trace["execution_status"] == body["execution_status"]
    assert trace["graph_steps"] == ["route", "sql_tool", "controller"]
    assert trace["route_decision"]["route"] == "sql"
    assert trace["evidence_refs"][0]["evidence_kind"] == "sql"
    assert trace["runtime_identity"]["status"] == "complete"
    assert trace["runtime_identity"]["route_runtime"]["runtime_ref"] == "text2sql-legacy-v1"


def test_rag_response_uses_validated_citations_and_trace_never_contains_document_body(tmp_path: Path) -> None:
    """RAG API 直接复用 AnswerFlow，`docs_used` 只能从 citation 单向派生。"""

    trace_path = tmp_path / "m35-rag.jsonl"
    with _client(trace_path) as client:
        response = client.post("/api/query", json={"question": "退款政策是什么？", "user_role": "ops"})

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert (body["route"], body["execution_status"], body["answer_status"], body["safety_status"]) == (
        "rag", "completed", "complete", "passed"
    )
    assert body["citations"]
    assert body["docs_used"] == [
        {key: citation[key] for key in ("citation_id", "title", "revision", "anchor")}
        for citation in body["citations"]
    ]
    assert trace["graph_steps"] == ["route", "rag_tool", "controller"]
    assert "context_characters" in trace["tool_observation"]["diagnostics"]
    # `content_identity` 是允许的不可逆 hash；递归检查的是没有正文 `content` 字段。
    def has_document_body(value: object) -> bool:
        """递归寻找真正正文 key，避免把 `content_identity` 哈希误判为正文。"""

        if isinstance(value, dict):
            return "content" in value or any(has_document_body(item) for item in value.values())
        if isinstance(value, list):
            return any(has_document_body(item) for item in value)
        return False

    assert has_document_body(trace) is False
    assert trace["runtime_identity"]["status"] == "complete"
    assert trace["runtime_identity"]["route_runtime"]["release_identity"]


def test_unknown_requested_role_fails_closed_before_sql_or_rag_tool(tmp_path: Path) -> None:
    """篡改 role 不会升级权限，也不泄露可用表或文档存在性。"""

    trace_path = tmp_path / "m35-untrusted.jsonl"
    with _client(trace_path) as client:
        response = client.post(
            "/api/query", json={"question": "各渠道订单量是多少？", "user_role": "super_admin", "force_new_pipeline": False}
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert (body["route"], body["execution_status"], body["answer_status"], body["safety_status"]) == (
        "none", "not_started", "no_answer", "blocked"
    )
    assert body["tool_calls"] == []
    assert body["tables_used"] == [] and body["docs_used"] == []
    assert trace["caller_safe_ref"] is None
    assert trace["graph_steps"] == ["route", "terminal", "controller"]
    assert trace["runtime_identity"]["route_runtime"] == {"kind": "none", "reason_code": "caller_untrusted"}
