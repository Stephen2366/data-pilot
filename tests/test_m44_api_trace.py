"""M44-F：T4/T5 API、Trace 与 TaskState 使用同一 AgentLoopResult。"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.task_boundary import TaskBoundary
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload, Evidence, EvidenceLedger, EvidenceRef, make_sql_evidence


def _sql_observation(request: HarnessRequest) -> ToolObservation:
    channel = "按渠道" in request.question
    rows = (
        ({"channel": "online", "increment": 40000}, {"channel": "store", "increment": 20000})
        if channel else ({"reason": "质量问题", "increment": 48000},)
    )
    evidence = make_sql_evidence(
        run_id=request.run_id, guarded_sql="SELECT safe_m44", columns=tuple(rows[0]),
        rows_count=len(rows), result_fingerprint=f"fp-{request.run_id}", queried_at="now",
        database_identity="fixture", runtime_identity="m44-api-fixture",
        safe_result_view=tuple(tuple(row.values()) for row in rows),
    )
    ledger = EvidenceLedger(
        request.run_id, (evidence,), ((evidence.ref.evidence_id, "generation_visible"),)
    )
    return ToolObservation(
        tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
        safety_status="passed", reason_code="sql_completed", answer="SQL 证据已取得。",
        sql="SELECT safe_m44", columns=tuple(rows[0]), rows=rows,
        evidence_refs=(evidence.ref.audit_projection(),), evidence_ledger=ledger,
        ledger_projection=ledger.safe_projection(), raw_evidence=(evidence,),
    )


class _SQLTool:
    def run(self, request: HarnessRequest) -> ToolObservation:
        return _sql_observation(request)

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


class _BusinessRAGTool:
    def run_for_hybrid(
        self, request: HarnessRequest, *, requirement: AnswerEvidenceRequirement
    ) -> ToolObservation:
        assert requirement.required_document_keys == ("refund_policy_basic", "refund_policy_quality")
        evidence = tuple(
            Evidence(
                EvidenceRef(request.run_id, f"doc-{key}", "document", "authority", "r1", f"content-{key}", key),
                ("answer_evidence",), "auth", "business-release",
                DocumentEvidencePayload("release-1", key, "r1", key, "policy", key, f"{key} 正文"),
            )
            for key in requirement.required_document_keys
        )
        ledger = EvidenceLedger(
            request.run_id, evidence,
            tuple((item.ref.evidence_id, "generation_visible") for item in evidence),
        )
        return ToolObservation(
            tool_name="rag_evidence_gate", route="rag", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="hybrid_document_evidence_ready",
            evidence_refs=tuple(item.ref.audit_projection() for item in evidence),
            evidence_ledger=ledger, ledger_projection=ledger.safe_projection(), raw_evidence=evidence,
            diagnostics={"candidate_count": 2, "selected_count": 2, "context_count": 2,
                         "knowledge_runtime_kind": "business_release"},
        )

    def run(self, request: HarnessRequest) -> ToolObservation:
        return self.run_for_hybrid(request, requirement=AnswerEvidenceRequirement())


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    def override_db() -> Generator[Session, None, None]:
        with Session(database) as session:
            yield session

    previous = (
        app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary,
        app.state.business_rag_tool_factory,
    )
    app.dependency_overrides[get_db] = override_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.sql_tool_factory = _SQLTool
    app.state.business_rag_tool_factory = _BusinessRAGTool
    app.state.task_boundary = TaskBoundary()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        (
            app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary,
            app.state.business_rag_tool_factory,
        ) = previous


def test_t4_t5_response_trace_and_state_are_same_source(tmp_path: Path) -> None:
    trace_path = tmp_path / "m44-api.jsonl"
    with _client(trace_path) as client:
        t4 = client.post("/api/query", json={
            "question": "比较 2026 年 7 月和 8 月实际净退款金额，并说明质量问题全额退款的前提和材料。",
            "task": {"action": "start"},
        }).json()
        t5 = client.post("/api/query", json={
            "question": "更正为按渠道比较 2026 年 7 月和 8 月，并重新核验退款政策。",
            "task": {"action": "continue", "task_id": t4["task"]["task_id"],
                     "expected_version": t4["task"]["task_version"]},
        }).json()
    traces = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    for body, trace in zip((t4, t5), traces):
        assert [item["action_id"] for item in body["action_attempts"]] == [
            "collect_sql_evidence", "collect_document_evidence"
        ]
        assert trace["action_attempts"] == body["action_attempts"]
        assert trace["agent_budget"] == body["agent_budget"]
        assert trace["agent_termination"] == body["agent_termination"]
        assert trace["knowledge_runtimes"] == body["knowledge_runtimes"]
        assert trace["agent_loop_runtime"] == body["agent_loop_runtime"]
        assert body["answer_status"] == "complete"
    assert t5["task_delta"]["category"] == "correct_previous_understanding"
    assert t5["task_transition"]["invalidated_evidence_count"] == 3
    assert [item["validity"] for item in t5["task"]["state"]["evidence"][:3]] == [
        "invalidated", "invalidated", "invalidated"
    ]


def test_client_cannot_inject_knowledge_scope_or_backend(tmp_path: Path) -> None:
    with _client(tmp_path / "m44-injection.jsonl") as client:
        response = client.post("/api/query", json={
            "question": "查询 2026 年 8 月实际净退款金额。",
            "task": {"action": "start", "knowledge_scope": "external_profile", "backend": "lexical"},
        })
    assert response.status_code == 422


def test_clarification_emits_only_nodes_that_actually_ran(tmp_path: Path) -> None:
    with _client(tmp_path / "m44-clarify-context.jsonl") as client:
        first = client.post("/api/query", json={
            "question": "查询 2026 年 8 月实际净退款金额。", "task": {"action": "start"},
        }).json()
        ambiguous = client.post("/api/query", json={
            "question": "改成另一个月。",
            "task": {"action": "continue", "task_id": first["task"]["task_id"],
                     "expected_version": first["task"]["task_version"]},
        }).json()
    assert ambiguous["graph_invocation_count"] == 0
    assert [item["purpose"] for item in ambiguous["node_contexts"]] == [
        "turn_understanding", "controller_response"
    ]
    assert ambiguous["action_attempts"] == []
