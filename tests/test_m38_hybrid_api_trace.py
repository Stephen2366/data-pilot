"""M38 真实 API/Trace 投影：同一 Hybrid run 不泄露私有 Evidence。"""

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
from scripts.seed_data import seed_database


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    """组装隔离 SQLite 与 trace，验证 API 没有调用任何 Hybrid 旁路。"""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        """让请求使用同一隔离 SQLite fixture。"""

        with Session(engine) as session:
            yield session

    previous_resolver = getattr(app.state, "caller_resolver", None)
    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver = previous_resolver
        Base.metadata.drop_all(engine)


def test_hybrid_response_and_trace_project_one_two_branch_run_without_raw_evidence(tmp_path: Path) -> None:
    """完整 Hybrid 同时引用 SQL/Document，JSONL 不保存 Document body 或完整 SQL rows。"""

    trace_path = tmp_path / "m38-hybrid.jsonl"
    with _client(trace_path) as client:
        response = client.post(
            "/api/query",
            json={"question": "查询退款原因并说明退款政策", "user_role": "ops", "force_new_pipeline": False},
        )

    body = response.json()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert response.status_code == 200
    assert (body["route"], body["execution_status"], body["answer_status"], body["safety_status"]) == (
        "hybrid", "completed", "complete", "passed"
    )
    assert {item["source_kind"] for item in body["citations"]} == {"sql", "document"}
    assert [item["branch"] for item in body["hybrid_branches"]] == ["sql", "rag"]
    assert trace["graph_steps"] == ["route", "hybrid_sql_tool", "hybrid_rag_tool", "controller"]
    assert trace["rows"] == []
    serialized = json.dumps(trace, ensure_ascii=False)
    assert "质量问题退款须" not in serialized
    assert '"content"' not in serialized
