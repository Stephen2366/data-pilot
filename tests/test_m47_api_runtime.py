"""M47-D/E：产品 durable 默认与跨 app restart API 纵向链。"""

from __future__ import annotations

from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation


class _SQLTool:
    """API restart 测试使用的零 provider 固定 SQL adapter。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        """返回单月或比较场景的固定安全 Observation。"""

        comparison = "差额" in request.question
        rows = (
            ({"period": "2026-07", "net_refund_amount": 120000}, {"period": "2026-08", "net_refund_amount": 180000})
            if comparison else ({"period": "2026-07", "net_refund_amount": 120000},)
        )
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="deterministic",
            sql="SELECT m47_oracle", columns=tuple(rows[0]), rows=rows, tables_used=("refunds",),
            evidence_refs=({"evidence_kind": "sql", "evidence_id": "m47", "result_fingerprint": "m47"},),
            diagnostics={"runtime_ref": "m47-deterministic-oracle-v1"},
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        """实现协议；本测试不会选择 hybrid route。"""

        return self.run(request)


def _settings(url: str, **extra) -> Settings:
    """构造显式 test 环境的 durable settings。"""

    return Settings(
        _env_file=None, APP_ENV="test", DATABASE_URL=url, TASK_BOUNDARY_BACKEND="mysql",
        DASHSCOPE_API_KEY="", **extra,
    )


def _app(url: str, trace: Path):
    """组装独立 app worker 并注入固定 caller/Tool/Trace。"""

    application = create_app(_settings(url))
    application.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    application.state.sql_tool_factory = _SQLTool
    application.state.trace_path = trace
    return application


def test_product_default_is_durable_and_memory_requires_test() -> None:
    """产品默认必须 durable，memory 不能在 local 误启用。"""

    assert Settings(_env_file=None).task_boundary_backend == "mysql"
    with pytest.raises(ValueError, match="APP_ENV=test"):
        create_app(Settings(_env_file=None, APP_ENV="local", TASK_BOUNDARY_BACKEND="memory"))
    app = create_app(Settings(_env_file=None, APP_ENV="test", TASK_BOUNDARY_BACKEND="memory"))
    assert app.state.task_boundary.runtime_identity["durability"] == "process_local_non_durable"


def test_restart_resume_uses_database_and_trace_matches(tmp_path: Path) -> None:
    """两个 app 生命周期间可恢复 task，Trace 标识 database 来源。"""

    url = f"sqlite+pysqlite:///{tmp_path / 'restart.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[AgentTaskCheckpoint.__table__, AgentTaskEvent.__table__])
    trace = tmp_path / "trace.jsonl"
    app_a = _app(url, trace)
    with TestClient(app_a) as client:
        first = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "user_role": "ops", "task": {"action": "start"}}).json()
    app_b = _app(url, trace)
    with TestClient(app_b) as client:
        second = client.post("/api/query", json={
            "question": "改成 8 月，并和 7 月比较。", "user_role": "ops",
            "task": {"action": "continue", "task_id": first["task"]["task_id"], "expected_version": first["task"]["task_version"]},
        }).json()
    assert second["task"]["task_version"] == 3
    assert second["task_delta"]["category"] == "modify_constraint"
    last_trace = json.loads(trace.read_text(encoding="utf-8").splitlines()[-1])
    assert last_trace["task_lifecycle"]["resume_source"] == "database"
    assert last_trace["runtime_identity"]["task_boundary"]["durability"] == "database_durable"
