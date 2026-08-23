"""M37 `/api/query` 与 JSONL Trace 的 bounded follow-up 增量合同。"""

from __future__ import annotations

import importlib
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
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.harness.thread import ThreadCheckpointManager
from engine.rag.evidence import EvidenceRef

query_api = importlib.import_module("app.api.query")


class _SQLAdapter:
    """每轮生成新 run Evidence，用于 HTTP/Trace 对账。"""

    calls = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, request: HarnessRequest) -> ToolObservation:
        type(self).calls += 1
        ref = EvidenceRef(
            request.run_id,
            f"sql-{request.run_id}",
            "sql",
            "fixture-db",
            f"query-{self.calls}",
            f"fingerprint-{self.calls}",
            "sql-result",
        )
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="sql_completed",
            answer=f"sql answer {self.calls}",
            rows=({"secret_old_row": self.calls},),
            evidence_refs=(ref.audit_projection(),),
            diagnostics={
                "result_fingerprint": ref.content_identity,
                "evidence_validity": {
                    "decision": "reacquired",
                    "reason": "sql_has_no_snapshot",
                    "old_new_relation": "changed",
                },
            },
        )


class _RAGAdapter:
    """本测试只走 SQL，保留独占 Tool 计数。"""

    calls = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, _request: HarnessRequest) -> ToolObservation:
        type(self).calls += 1
        raise AssertionError("SQL sequence 不得调用 RAG")


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(database)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(database) as session:
            yield session

    previous_resolver = getattr(app.state, "caller_resolver", None)
    previous_manager = getattr(app.state, "thread_checkpoint_manager", None)
    previous_rag_factory = getattr(app.state, "rag_tool_factory", None)
    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.thread_checkpoint_manager = ThreadCheckpointManager()
    app.state.rag_tool_factory = lambda: query_api.RAGToolAdapter()
    _SQLAdapter.calls = _RAGAdapter.calls = 0
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver = previous_resolver
        app.state.thread_checkpoint_manager = previous_manager
        app.state.rag_tool_factory = previous_rag_factory
        Base.metadata.drop_all(database)


def test_opt_in_sql_follow_up_projects_spec_and_safe_trace(tmp_path: Path, monkeypatch: object) -> None:
    """响应公开表单；Trace 记录 validity，但不保存 raw thread id 或 follow-up 字段值。"""

    monkeypatch.setattr(query_api, "Text2SQLToolAdapter", _SQLAdapter)
    monkeypatch.setattr(query_api, "RAGToolAdapter", _RAGAdapter)
    trace_path = tmp_path / "m37-follow-up.jsonl"
    with _client(trace_path) as client:
        initial = client.post(
            "/api/query",
            json={
                "question": "各渠道订单量是多少？",
                "user_role": "ops",
                "enable_bounded_follow_up": True,
            },
        )
        ready = initial.json()["thread"]
        followed = client.post(
            "/api/query",
            json={
                "question": "执行结构化追问",
                "user_role": "ops",
                "thread_id": ready["thread_id"],
                "expected_version": ready["checkpoint_version"],
                "follow_up_action": "adjust_sql_scope",
                "follow_up_fields": {"time_range": "2026年7月", "group_by": "商品"},
            },
        )

    assert initial.status_code == followed.status_code == 200
    assert ready["status"] == "follow_up_ready" and ready["follow_up_budget_remaining"] == 1
    assert ready["follow_up"]["actions"][0]["action"] == "adjust_sql_scope"
    assert (followed.json()["turn_action"], followed.json()["thread"]["status"]) == (
        "follow_up", "resolved"
    )
    assert _SQLAdapter.calls == 2 and _RAGAdapter.calls == 0

    traces = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [item["turn_action"] for item in traces] == ["initial", "follow_up"]
    assert traces[1]["tool_observation"]["diagnostics"]["evidence_validity"]["decision"] == "reacquired"
    serialized = json.dumps(traces, ensure_ascii=False)
    assert ready["thread_id"] not in serialized
    assert "2026年7月" not in serialized and '"group_by": "商品"' not in serialized


def test_api_rejects_mixed_or_half_follow_up_shapes_before_handler() -> None:
    """HTTP schema 不猜测半截/mixed turn。"""

    with TestClient(app) as client:
        half = client.post(
            "/api/query",
            json={"question": "x", "thread_id": "t", "expected_version": 1},
        )
        mixed = client.post(
            "/api/query",
            json={
                "question": "x",
                "thread_id": "t",
                "expected_version": 1,
                "clarification_answers": {"subject": "退款政策"},
                "follow_up_action": "explain_same_evidence",
                "follow_up_fields": {"style": "通俗说明"},
            },
        )
    assert half.status_code == mixed.status_code == 422
