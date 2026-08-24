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
from app.schemas.agent import ToolCallTrace
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.task_boundary import TaskBoundary
from engine.rag.answer_flow import AnswerEvidenceRequirement
from engine.rag.evidence import DocumentEvidencePayload, Evidence, EvidenceLedger, EvidenceRef, make_sql_evidence
from engine.trace.recorder import TraceStep


_RAW_DB_ERROR = "RAW_DB_DRIVER_DETAIL_MUST_NOT_ESCAPE"


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


class _RawDatabaseFailureSQLTool:
    """模拟 adapter 误塞 raw error，验证公开 API/Trace 边界仍能 fail closed。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        del request
        return ToolObservation(
            tool_name="text2sql",
            route="sql",
            execution_status="failed",
            answer_status="no_answer",
            safety_status="passed",
            reason_code="sql_execution_error",
            answer="当前无法完成数据查询，请稍后再试。",
            sql="SELECT DATE_TRUNC('month', processed_at) FROM refunds",
            tool_calls=(ToolCallTrace(
                tool_name="sql_query",
                status="error",
                error_type="sql_execution_error",
                message=_RAW_DB_ERROR,
            ),),
            trace_steps=(TraceStep(
                name="sql_execution",
                step_index=1,
                step_type="sql_query",
                status="error",
                output_summary=_RAW_DB_ERROR,
                error_type="sql_execution_error",
                metadata={"raw_error": _RAW_DB_ERROR, "tables_used": ["refunds"]},
            ),),
            error_type="sql_execution_error",
            diagnostics={"technical_message": _RAW_DB_ERROR},
        )

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
def _client(trace_path: Path, *, sql_tool_factory: type = _SQLTool) -> Generator[TestClient, None, None]:
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
    app.state.sql_tool_factory = sql_tool_factory
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


def test_raw_database_error_is_removed_from_api_and_trace(tmp_path: Path) -> None:
    """公开投影是最后一道保险：adapter 带入 raw error 时也不能出现在 Response/Trace。"""

    trace_path = tmp_path / "m44-safe-sql-error.jsonl"
    with _client(trace_path, sql_tool_factory=_RawDatabaseFailureSQLTool) as client:
        body = client.post("/api/query", json={
            "question": "查询 2026 年 8 月实际净退款金额。",
            "task": {"action": "start"},
        }).json()
    trace = json.loads(trace_path.read_text(encoding="utf-8").strip())

    assert _RAW_DB_ERROR not in json.dumps(body, ensure_ascii=False)
    assert _RAW_DB_ERROR not in json.dumps(trace, ensure_ascii=False)
    assert body["tool_calls"][0]["message"] == "SQL 执行失败。"
    assert trace["tool_calls"] == body["tool_calls"]
    assert trace["trace_steps"][0]["output_summary"] == "SQL 执行失败。"
    assert trace["trace_steps"][0]["metadata"] == {"tables_used": ["refunds"]}
