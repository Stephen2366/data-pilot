"""M43-E 同一 API 的 task envelope、T1/T2、Trace 与 lifecycle clear。"""

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


class _B1SQLTool:
    """确定性 rehearsal tool：只模拟已冻结 oracle，不调用 LLM 或外部服务。"""

    calls = 0

    def run(self, request: HarnessRequest) -> ToolObservation:
        type(self).calls += 1
        comparison = "并计算差额" in request.question
        august_only = "8 月" in request.question and not comparison
        rows = (
            ({"period": "2026-07", "net_refund_amount": 120000}, {"period": "2026-08", "net_refund_amount": 180000})
            if comparison else (({"period": "2026-08", "net_refund_amount": 180000},) if august_only else ({"period": "2026-07", "net_refund_amount": 120000},))
        )
        answer = "8 月为 180000。" if august_only else ("7 月为 120000。" if not comparison else "SQL 已返回两个月的基础金额。")
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer=answer, sql="SELECT safe_b1_oracle",
            columns=tuple(rows[0]), rows=rows, tables_used=("refunds",),
            evidence_refs=({"evidence_kind": "sql", "evidence_id": f"b1-{type(self).calls}", "result_fingerprint": f"fp-{type(self).calls}"},),
            diagnostics={"runtime_ref": "m43-deterministic-oracle-v1"},
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


@contextmanager
def _client(trace_path: Path) -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    def override_get_db() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    previous = (app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary)
    app.dependency_overrides[get_db] = override_get_db
    app.state.trace_path = trace_path
    app.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    app.state.sql_tool_factory = _B1SQLTool
    app.state.task_boundary = TaskBoundary()
    _B1SQLTool.calls = 0
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        delattr(app.state, "trace_path")
        app.state.caller_resolver, app.state.sql_tool_factory, app.state.task_boundary = previous


def test_canonical_t1_t2_share_task_fact_and_requery_after_invalidation(tmp_path: Path) -> None:
    trace_path = tmp_path / "m43.jsonl"
    with _client(trace_path) as client:
        first = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "user_role": "ops", "task": {"action": "start"}})
        first_body = first.json()
        second = client.post("/api/query", json={"question": "改成 8 月，并和 7 月比较。", "user_role": "ops", "task": {"action": "continue", "task_id": first_body["task"]["task_id"], "expected_version": first_body["task"]["task_version"]}})
    body = second.json()
    traces = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert first.status_code == second.status_code == 200
    assert _B1SQLTool.calls == 2
    assert body["runtime_family"] == "agent_task" and body["task_delta"]["category"] == "modify_constraint"
    assert body["rows"][1] == {"period": "2026-08", "net_refund_amount": 180000, "delta": 60000, "rate": 0.5}
    assert "增加 60000" in body["answer"] and "50%" in body["answer"]
    validity = [item["validity"] for item in body["task"]["state"]["evidence"]]
    assert validity == ["invalidated", "active"]
    assert body["task_transition"]["invalidated_evidence_count"] == 1
    assert body["graph_invocation_count"] == body["task_runtime_invocation_count"] == 1
    assert traces[1]["task_state"] == body["task"]["state"]
    assert traces[1]["task_delta"] == body["task_delta"]
    assert traces[1]["node_contexts"] == body["node_contexts"]
    assert traces[1]["task_transition"]["after_identity"] == traces[1]["task_lifecycle"]["state_identity"]
    assert traces[1]["runtime_identity"]["format"] == "phase4b-agent-task-runtime-v1"
    assert traces[1]["runtime_identity"]["contract_identity"]
    assert traces[1]["rows"] == body["rows"]
    assert traces[1]["tool_observation"]["diagnostics"]["comparison_completion"]["status"] == "complete"


def test_clarify_cancel_clear_and_pre_rejection_never_call_graph(tmp_path: Path) -> None:
    trace_path = tmp_path / "m43-zero.jsonl"
    with _client(trace_path) as client:
        started = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "task": {"action": "start"}}).json()
        task = started["task"]
        ambiguous = client.post("/api/query", json={"question": "改成另一个月。", "task": {"action": "continue", "task_id": task["task_id"], "expected_version": task["task_version"]}}).json()
        cancelled = client.post("/api/query", json={"question": "取消任务。", "task": {"action": "cancel", "task_id": ambiguous["task"]["task_id"], "expected_version": ambiguous["task"]["task_version"]}}).json()
        rejected = client.post("/api/query", json={"question": "继续", "task": {"action": "continue", "task_id": task["task_id"], "expected_version": task["task_version"]}}).json()
        fresh = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "task": {"action": "start"}}).json()
        cleared = client.delete(f"/api/query/tasks/{fresh['task']['task_id']}", params={"expected_version": fresh["task"]["task_version"], "user_role": "ops"})
    assert ambiguous["answer_status"] == "clarification_required" and ambiguous["graph_invocation_count"] == 0
    assert cancelled["task_action"] == "cancel" and cancelled["graph_invocation_count"] == 0
    assert rejected["task_action"] == "rejected" and rejected["task_runtime_invocation_count"] == 0
    assert cleared.status_code == 200 and cleared.json()["task"]["status"] == "cleared"
    assert _B1SQLTool.calls == 2


def test_task_envelope_is_strict_but_legacy_top_level_compatibility_remains(tmp_path: Path) -> None:
    with _client(tmp_path / "shape.jsonl") as client:
        strict = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "task": {"action": "start", "route": "sql"}})
        mixed = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "thread_id": "x", "expected_version": 1, "clarification_answers": {"subject": "x"}, "task": {"action": "start"}})
        legacy = client.post("/api/query", json={"question": "各渠道订单量是多少？", "force_new_pipeline": False, "old_client_extra": "ignored"})
    assert strict.status_code == mixed.status_code == 422
    assert legacy.status_code == 200 and legacy.json()["runtime_family"] == "legacy"


def test_correction_and_switch_are_independent_api_lifecycles(tmp_path: Path) -> None:
    with _client(tmp_path / "correction-switch.jsonl") as client:
        first = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "task": {"action": "start"}}).json()
        corrected = client.post("/api/query", json={"question": "更正为 2026 年 8 月实际净退款金额。", "task": {"action": "continue", "task_id": first["task"]["task_id"], "expected_version": first["task"]["task_version"]}}).json()
        switched = client.post("/api/query", json={"question": "换个问题，查询 2026 年 7 月实际净退款金额。", "task": {"action": "switch", "task_id": corrected["task"]["task_id"], "expected_version": corrected["task"]["task_version"]}}).json()
        old = client.post("/api/query", json={"question": "继续", "task": {"action": "continue", "task_id": corrected["task"]["task_id"], "expected_version": corrected["task"]["task_version"]}}).json()
    assert corrected["task_delta"]["category"] == "correct_previous_understanding"
    assert corrected["rows"] == [{"period": "2026-08", "net_refund_amount": 180000}]
    assert switched["task"]["task_id"] != corrected["task"]["task_id"]
    assert switched["task"]["state"]["generation"] == 1 and len(switched["task"]["state"]["evidence"]) == 1
    assert old["task_action"] == "rejected" and old["graph_invocation_count"] == 0
