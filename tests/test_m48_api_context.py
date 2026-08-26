"""M48-D：API 连续 task、Compact trigger 与安全 Trace 接线。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation


class _SQLTool:
    """零 provider 的 Phase 4B SQL oracle adapter。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="120000",
            sql="SELECT m48_oracle", columns=("period", "net_refund_amount"),
            rows=({"period": "2026-07", "net_refund_amount": 120000},), tables_used=("refunds",),
            evidence_refs=({"evidence_kind": "sql", "evidence_id": "m48:120000", "result_fingerprint": "m48"},),
            diagnostics={"runtime_ref": "m48-deterministic-oracle-v1"},
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        return self.run(request)


def _app(url: str, trace: Path):
    application = create_app(Settings(
        _env_file=None, APP_ENV="test", DATABASE_URL=url, TASK_BOUNDARY_BACKEND="mysql",
        DASHSCOPE_API_KEY="",
    ))
    application.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    application.state.sql_tool_factory = _SQLTool
    application.state.trace_path = trace
    return application


def test_sixth_api_turn_compacts_five_committed_turns_and_redacts_raw(tmp_path: Path) -> None:
    """同一 raw task 第六轮执行前 compact；Response/Trace 不泄露 recent raw。"""

    url = f"sqlite+pysqlite:///{tmp_path / 'm48-api.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AgentTaskCheckpoint.__table__, AgentTaskEvent.__table__])
    trace = tmp_path / "trace.jsonl"
    app = _app(url, trace)
    with TestClient(app) as client:
        current = client.post("/api/query", json={
            "question": "查询 2026 年 7 月实际净退款金额。", "user_role": "ops",
            "task": {"action": "start"},
        }).json()
        for ordinal in range(2, 7):
            current = client.post("/api/query", json={
                "question": f"继续查询 2026 年 7 月实际净退款金额，第 {ordinal} 轮。",
                "user_role": "ops",
                "task": {
                    "action": "continue", "task_id": current["task"]["task_id"],
                    "expected_version": current["task"]["task_version"],
                },
            }).json()
    assert current["compact_decision"]["outcome"] == "triggered_and_committed"
    assert current["compact_decision"]["trigger"] == "committed_turns"
    assert current["task_context"]["compact_source_turn_range"] == [1, 5]
    assert current["task_context"]["uncovered_turn_count"] == 1
    assert current["task_context"]["recent_raw_turn_count"] == 2
    serialized = json.dumps(current, ensure_ascii=False)
    # Response 的 node Context 只保留 question/recent 的 hash；原文不会复制进响应。
    assert "第 5 轮" not in serialized
    assert current["node_contexts"][0]["payload"]["question"]["redacted"] is True
    last_trace = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
    assert last_trace["compact_decision"]["compact_identity"] == current["task_context"]["compact_identity"]
    assert "第 5 轮" not in json.dumps(last_trace, ensure_ascii=False)


def test_switch_starts_a_fresh_context_lineage_at_version_one(tmp_path: Path) -> None:
    """switch 只沿用旧 task 的授权事实；新 task 的 Context 必须从 T1/version=1 重建。"""

    url = f"sqlite+pysqlite:///{tmp_path / 'm48-switch.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AgentTaskCheckpoint.__table__, AgentTaskEvent.__table__])
    app = _app(url, tmp_path / "switch-trace.jsonl")
    with TestClient(app) as client:
        first = client.post("/api/query", json={
            "question": "查询 2026 年 7 月实际净退款金额。", "user_role": "ops",
            "task": {"action": "start"},
        }).json()
        continued = client.post("/api/query", json={
            "question": "更正为 2026 年 8 月实际净退款金额。", "user_role": "ops",
            "task": {
                "action": "continue", "task_id": first["task"]["task_id"],
                "expected_version": first["task"]["task_version"],
            },
        }).json()
        switched = client.post("/api/query", json={
            "question": "换个问题，查询 2026 年 7 月实际净退款金额。", "user_role": "ops",
            "task": {
                "action": "switch", "task_id": continued["task"]["task_id"],
                "expected_version": continued["task"]["task_version"],
            },
        }).json()

    assert switched["task_action"] == "switch"
    assert switched["task"]["task_id"] != continued["task"]["task_id"]
    assert switched["task"]["task_version"] == 1
    assert switched["task_context"]["source_watermark"] == 1
    assert switched["task_context"]["uncovered_turn_count"] == 1
    assert switched["task_context"]["compact_identity"] is None
