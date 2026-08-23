"""M40 P7：五条真实 HTTP 路径共用同源 response / JSONL Trace 的 rehearsal。"""

from __future__ import annotations

import json
from hashlib import sha256
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from engine.harness.caller import FixtureCallerResolver
from engine.harness.adapters import RAGToolAdapter
from engine.harness.thread import ThreadCheckpointManager
from eval.phase4_assurance import (
    REHEARSAL_SCENARIOS,
    TraceRehearsalEvidence,
    build_trace_rehearsal_artifact,
    rehearsal_artifact_from_json,
    rehearsal_artifact_to_json,
)
from scripts.seed_data import seed_database


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    """隔离 SQLite、caller、checkpoint 与 JSONL，保证演练不读取真实 provider。"""

    database = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(database)
    with Session(database) as session:
        seed_database(session, reset_existing=True)

    def override_get_db() -> Generator[Session, None, None]:
        """让每个 API 请求使用同一份隔离的种子数据。"""

        with Session(database) as session:
            yield session

    previous_resolver = getattr(app.state, "caller_resolver", None)
    previous_manager = getattr(app.state, "thread_checkpoint_manager", None)
    previous_rag_factory = getattr(app.state, "rag_tool_factory", None)
    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.thread_checkpoint_manager = ThreadCheckpointManager()
    app.state.rag_tool_factory = lambda: RAGToolAdapter()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver = previous_resolver
        app.state.thread_checkpoint_manager = previous_manager
        app.state.rag_tool_factory = previous_rag_factory
        Base.metadata.drop_all(database)


def _read_traces(path: Path) -> list[dict[str, Any]]:
    """JSONL 的每一行都代表一条 turn；不把多轮序列压扁成最终结果。"""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _contains_forbidden_key(value: object) -> bool:
    """Trace 可保留 content identity hash，但不可长期保存正文 content 字段。"""

    if isinstance(value, dict):
        return "content" in value or any(_contains_forbidden_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _assert_same_turn(response: dict[str, Any], trace: dict[str, Any]) -> None:
    """响应与 Trace 的 ID、四轴和 route 必须来自同一 AgentTurnResult。"""

    assert trace["trace_id"] == response["trace_id"]
    assert trace["route"] == response["route"]
    assert (
        trace["execution_status"], trace["answer_status"], trace["safety_status"]
    ) == (response["execution_status"], response["answer_status"], response["safety_status"])
    assert trace["runtime_identity"]["status"] == "complete"


def _execution_identity(*, responses: list[dict[str, Any]], traces: list[dict[str, Any]]) -> str:
    """把同次 response/Trace 的安全对应事实压成不可逆来源指纹，不把正文放入 artifact。"""

    payload = [
        {
            "trace_id": trace["trace_id"], "route": trace["route"],
            "axes": [trace["execution_status"], trace["answer_status"], trace["safety_status"]],
            "response_trace_id": response["trace_id"], "runtime_identity": trace["runtime_identity"],
            "evidence_refs": trace["evidence_refs"], "hybrid_branches": trace["hybrid_branches"],
            "thread_lifecycle": trace["thread_lifecycle"], "graph_invocation_count": trace["graph_invocation_count"],
        }
        for response, trace in zip(responses, traces, strict=True)
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "trace-rehearsal:" + sha256(encoded).hexdigest()


def test_five_path_rehearsal_builds_a_closed_world_safe_artifact(tmp_path: Path) -> None:
    """五条 canonical API 故事各只执行一次，并产出可给 C3 消费的安全 C2 artifact。"""

    trace_path = tmp_path / "m40-five-paths.jsonl"
    with _client(trace_path) as client:
        sql = client.post(
            "/api/query", json={"question": "各渠道订单量是多少？", "user_role": "ops", "force_new_pipeline": False}
        )
        rag = client.post("/api/query", json={"question": "退款政策是什么？", "user_role": "ops"})
        hybrid = client.post(
            "/api/query", json={"question": "查询退款原因并说明退款政策", "user_role": "ops", "force_new_pipeline": False}
        )
        clarification = client.post("/api/query", json={"question": "这个怎么处理？", "user_role": "ops"})
        pending = clarification.json()["thread"]
        resumed = client.post(
            "/api/query",
            json={
                "question": "补充主体",
                "user_role": "ops",
                "thread_id": pending["thread_id"],
                "expected_version": pending["checkpoint_version"],
                "clarification_answers": {"subject": "退款政策"},
            },
        )
        rejected = client.post(
            "/api/query", json={"question": "各渠道订单量是多少？", "user_role": "super_admin", "force_new_pipeline": False}
        )

    responses = [item.json() for item in (sql, rag, hybrid, clarification, resumed, rejected)]
    assert all(item.status_code == 200 for item in (sql, rag, hybrid, clarification, resumed, rejected))
    traces = _read_traces(trace_path)
    assert len(traces) == len(responses) == 6
    sql_trace, rag_trace, hybrid_trace, clarification_trace, resumed_trace, rejected_trace = traces
    sql_body, rag_body, hybrid_body, clarification_body, resumed_body, rejected_body = responses

    # 1. SQL：一次 Graph / Tool，EvidenceRef 与 runtime ref 都能回查。----------
    _assert_same_turn(sql_body, sql_trace)
    assert (sql_trace["graph_invocation_count"], sql_trace["graph_steps"]) == (1, ["route", "sql_tool", "controller"])
    assert sql_trace["evidence_refs"] and sql_trace["runtime_identity"]["route_runtime"]["runtime_ref"]

    # 2. RAG：citation 和 Trace Evidence 同轮，且 runtime identity 齐全。----------
    _assert_same_turn(rag_body, rag_trace)
    assert rag_body["citations"] and rag_trace["evidence_refs"]
    # API 只公开 citation 的最小 document 坐标；Trace EvidenceRef 保留同一坐标的安全 identity。
    assert {
        (item["authority_identity"], item["revision"], item["anchor"])
        for item in rag_trace["evidence_refs"]
    } >= {
        (item["authority_ref"], item["revision"], item["anchor"])
        for item in rag_body["citations"]
    }
    assert rag_trace["runtime_identity"]["route_runtime"]["answer_flow_identity"]

    # 3. Hybrid：固定两支、一个 Graph；Trace 不保存完整 SQL rows。----------
    _assert_same_turn(hybrid_body, hybrid_trace)
    assert hybrid_trace["graph_invocation_count"] == 1 and hybrid_trace["rows"] == []
    assert [item["branch"] for item in hybrid_trace["hybrid_branches"]] == ["sql", "rag"]
    assert hybrid_trace["runtime_identity"]["route_runtime"]["synthesizer_identity"]

    # 4. 澄清恢复：initial / resume 是两个明确 turn，不保存 raw thread 或填写值。----------
    _assert_same_turn(clarification_body, clarification_trace)
    _assert_same_turn(resumed_body, resumed_trace)
    assert [clarification_trace["turn_action"], resumed_trace["turn_action"]] == ["initial", "resume"]
    assert clarification_trace["graph_invocation_count"] == resumed_trace["graph_invocation_count"] == 1
    assert resumed_trace["thread_lifecycle"]["version_before"] == pending["checkpoint_version"]

    # 5. 安全拒绝：正确的 pre-Graph 拒绝也有完整 lifecycle/runtime Trace。----------
    _assert_same_turn(rejected_body, rejected_trace)
    assert (rejected_trace["route"], rejected_trace["safety_status"], rejected_trace["graph_invocation_count"]) == (
        "none", "blocked", 1
    )
    assert rejected_trace["tool_calls"] == [] and rejected_trace["caller_safe_ref"] is None

    # answer 可以按旧 Trace 合同自然复述业务主题；这里仅禁止直接持久化 thread 参数结构或 id。
    thread_serialized = json.dumps([clarification_trace, resumed_trace], ensure_ascii=False)
    assert pending["thread_id"] not in thread_serialized
    assert '"clarification_answers"' not in thread_serialized and '"follow_up_fields"' not in thread_serialized
    assert _contains_forbidden_key(traces) is False
    evidence = (
        TraceRehearsalEvidence("sql", 1, True, True, True, "complete", True, _execution_identity(responses=[sql_body], traces=[sql_trace])),
        TraceRehearsalEvidence("rag", 1, True, True, True, "complete", True, _execution_identity(responses=[rag_body], traces=[rag_trace])),
        TraceRehearsalEvidence("hybrid", 1, True, True, True, "complete", True, _execution_identity(responses=[hybrid_body], traces=[hybrid_trace])),
        TraceRehearsalEvidence("clarification_resume", 2, True, True, True, "complete", True, _execution_identity(responses=[clarification_body, resumed_body], traces=[clarification_trace, resumed_trace])),
        TraceRehearsalEvidence("safety_rejection", 1, True, True, True, "complete", True, _execution_identity(responses=[rejected_body], traces=[rejected_trace])),
    )
    artifact = build_trace_rehearsal_artifact(evidence)
    assert tuple(item.scenario_id for item in artifact.execution_evidence) == REHEARSAL_SCENARIOS
    assert rehearsal_artifact_from_json(rehearsal_artifact_to_json(artifact)) == artifact
