"""M36 API / Trace 多轮回归：HTTP 只投影 turn seam，不自行管理 checkpoint。"""

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

query_api = importlib.import_module("app.api.query")


class _FakeSQLAdapter:
    """替代真实 Text2SQL，证明 API resume 只调用一次目标 Tool。"""

    calls = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 SQL 结果，并记录真实调用次数。"""

        type(self).calls += 1
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="sql_completed",
            answer="sql answer",
        )


class _FakeRAGAdapter:
    """替代真实 RAGAnswerFlow，避免 API 合同测试依赖外部检索。"""

    calls = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    def run(self, _request: HarnessRequest) -> ToolObservation:
        """返回固定 RAG 结果，并记录真实调用次数。"""

        type(self).calls += 1
        return ToolObservation(
            tool_name="rag_answer_flow",
            route="rag",
            execution_status="completed",
            answer_status="complete",
            safety_status="passed",
            reason_code="answer_completed",
            answer="rag answer",
        )


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    """隔离 DB、Trace、caller 与 checkpoint，确保 sequence 之间没有共享状态。"""

    database = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(database)

    def override_get_db() -> Generator[Session, None, None]:
        """让 TestClient 使用隔离的内存数据库 Session。"""

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
    _FakeSQLAdapter.calls = _FakeRAGAdapter.calls = 0
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver = previous_resolver
        app.state.thread_checkpoint_manager = previous_manager
        app.state.rag_tool_factory = previous_rag_factory
        Base.metadata.drop_all(database)


def _read_traces(path: Path) -> list[dict[str, object]]:
    """JSONL 的每一行就是一个 turn，不能把多轮覆盖成单份报告。"""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_analytics_resume_projects_versions_and_safe_trace(tmp_path: Path, monkeypatch: object) -> None:
    """initial pending → SQL resume 保留版本链，Trace 不保存 raw thread id/答案值。"""

    monkeypatch.setattr(query_api, "Text2SQLToolAdapter", _FakeSQLAdapter)
    monkeypatch.setattr(query_api, "RAGToolAdapter", _FakeRAGAdapter)
    trace_path = tmp_path / "m36-analytics.jsonl"
    with _client(trace_path) as client:
        initial = client.post("/api/query", json={"question": "退款情况怎么样？", "user_role": "ops"})
        pending = initial.json()["thread"]
        resumed = client.post(
            "/api/query",
            json={
                "question": "补充统计条件",
                "user_role": "ops",
                "thread_id": pending["thread_id"],
                "expected_version": pending["checkpoint_version"],
                "clarification_answers": {"time_range": "2026年6月", "group_by": "渠道"},
            },
        )

    initial_body, resumed_body = initial.json(), resumed.json()
    traces = _read_traces(trace_path)
    assert initial.status_code == resumed.status_code == 200
    assert (initial_body["answer_status"], initial_body["graph_invocation_count"]) == (
        "clarification_required",
        1,
    )
    assert [field["key"] for field in pending["clarification"]["fields"]] == ["time_range", "group_by"]
    assert (resumed_body["route"], resumed_body["thread"]["status"]) == ("sql", "resolved")
    assert _FakeSQLAdapter.calls == 1 and _FakeRAGAdapter.calls == 0
    assert [trace["turn_action"] for trace in traces] == ["initial", "resume"]
    assert traces[0]["thread_lifecycle"]["version_after"] == 1
    assert (traces[1]["thread_lifecycle"]["version_before"], traces[1]["thread_lifecycle"]["version_after"]) == (
        1,
        3,
    )
    serialized = "\n".join(json.dumps(trace, ensure_ascii=False) for trace in traces)
    assert pending["thread_id"] not in serialized
    assert "2026年6月" not in serialized and '"group_by": "渠道"' not in serialized


def test_subject_resume_reaches_rag_and_duplicate_is_pregraph_rejected(
    tmp_path: Path, monkeypatch: object
) -> None:
    """缺主体可恢复到 RAG；同 version 重放只写拒绝事实，不再调用 Tool。"""

    monkeypatch.setattr(query_api, "Text2SQLToolAdapter", _FakeSQLAdapter)
    monkeypatch.setattr(query_api, "RAGToolAdapter", _FakeRAGAdapter)
    trace_path = tmp_path / "m36-subject.jsonl"
    with _client(trace_path) as client:
        initial = client.post("/api/query", json={"question": "这个怎么处理？", "user_role": "ops"})
        pending = initial.json()["thread"]
        payload = {
            "question": "补充主体",
            "user_role": "ops",
            "thread_id": pending["thread_id"],
            "expected_version": pending["checkpoint_version"],
            "clarification_answers": {"subject": "退款政策"},
        }
        resumed = client.post("/api/query", json=payload)
        duplicate = client.post("/api/query", json=payload)

    assert (resumed.json()["route"], resumed.json()["turn_action"]) == ("rag", "resume")
    assert (duplicate.json()["reason_code"], duplicate.json()["graph_invocation_count"]) == (
        "thread_already_resumed",
        0,
    )
    assert _FakeRAGAdapter.calls == 1
    assert [trace["graph_invocation_count"] for trace in _read_traces(trace_path)] == [1, 1, 0]


def test_clear_endpoint_invalidates_pending_without_graph(tmp_path: Path, monkeypatch: object) -> None:
    """显式 clear 形成独立 lifecycle Trace，之后 resume 在 Graph 前停止。"""

    monkeypatch.setattr(query_api, "Text2SQLToolAdapter", _FakeSQLAdapter)
    monkeypatch.setattr(query_api, "RAGToolAdapter", _FakeRAGAdapter)
    trace_path = tmp_path / "m36-clear.jsonl"
    with _client(trace_path) as client:
        initial = client.post("/api/query", json={"question": "这个怎么处理？", "user_role": "ops"})
        pending = initial.json()["thread"]
        cleared = client.delete(
            f"/api/query/threads/{pending['thread_id']}",
            params={"user_role": "ops", "expected_version": pending["checkpoint_version"]},
        )
        rejected = client.post(
            "/api/query",
            json={
                "question": "补充主体",
                "user_role": "ops",
                "thread_id": pending["thread_id"],
                "expected_version": cleared.json()["thread"]["checkpoint_version"],
                "clarification_answers": {"subject": "退款政策"},
            },
        )

    assert (cleared.json()["ok"], cleared.json()["thread"]["status"]) == (True, "cleared")
    assert (rejected.json()["reason_code"], rejected.json()["graph_invocation_count"]) == ("thread_cleared", 0)
    traces = _read_traces(trace_path)
    assert [(trace["turn_action"], trace["graph_invocation_count"]) for trace in traces] == [
        ("initial", 1),
        ("clear", 0),
        ("rejected", 0),
    ]
    assert _FakeSQLAdapter.calls == _FakeRAGAdapter.calls == 0
