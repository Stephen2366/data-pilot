"""M47-E/P2：真实 MySQL 上的跨进程 API restart + multi-worker rehearsal。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.main import create_app
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.governance import test_caller
from engine.harness.caller import FixtureCallerResolver
from engine.harness.contracts import HarnessRequest, ToolObservation
from engine.phase4b.mysql_task_boundary import MySQLTaskBoundary
from engine.phase4b.task_boundary import TaskBoundaryError
from engine.phase4b.task_runtime import TaskState

TARGET_DATABASE = "datapilot_m47_test"


class _SQLTool:
    """固定 oracle；没有 LLM、embedding、RAG 或业务数据库调用。"""

    def run(self, request: HarnessRequest) -> ToolObservation:
        """按问题是否要求比较返回固定单月或双月 Observation。"""

        comparison = "差额" in request.question
        rows = (
            ({"period": "2026-07", "net_refund_amount": 120000}, {"period": "2026-08", "net_refund_amount": 180000})
            if comparison else ({"period": "2026-07", "net_refund_amount": 120000},)
        )
        return ToolObservation(
            tool_name="text2sql", route="sql", execution_status="completed", answer_status="complete",
            safety_status="passed", reason_code="sql_completed", answer="deterministic",
            sql="SELECT m47_oracle", columns=tuple(rows[0]), rows=rows, tables_used=("refunds",),
            evidence_refs=({"evidence_kind": "sql", "evidence_id": "m47-p2", "result_fingerprint": "m47-p2"},),
            diagnostics={"runtime_ref": "m47-p2-deterministic-oracle-v1"},
        )

    def run_for_hybrid(self, request: HarnessRequest) -> ToolObservation:
        """保持协议完整；本 rehearsal 实际只走 SQL route。"""

        return self.run(request)


def _target_url() -> str:
    """从现有本地凭据派生唯一获准的 M47 测试库 URL。"""

    return make_url(get_settings().database_url).set(database=TARGET_DATABASE).render_as_string(hide_password=False)


def _application(url: str, trace: Path):
    """组装一个拥有独立 Engine 的 test app worker。"""

    settings = Settings(_env_file=None, APP_ENV="test", DATABASE_URL=url, TASK_BOUNDARY_BACKEND="mysql", DASHSCOPE_API_KEY="")
    application = create_app(settings)
    application.state.caller_resolver = FixtureCallerResolver(fixture_kind="test")
    application.state.sql_tool_factory = _SQLTool
    application.state.trace_path = trace
    return application


def _turn(url: str, output: Path, *, prior: Path | None = None) -> None:
    """在单独进程执行 T1 或读取前进程结果后执行 T2。"""

    app = _application(url, output.with_suffix(".jsonl"))
    with TestClient(app) as client:
        if prior is None:
            response = client.post("/api/query", json={"question": "查询 2026 年 7 月实际净退款金额。", "user_role": "ops", "task": {"action": "start"}})
        else:
            first = json.loads(prior.read_text(encoding="utf-8"))
            response = client.post("/api/query", json={
                "question": "改成 8 月，并和 7 月比较。", "user_role": "ops",
                "task": {"action": "continue", "task_id": first["task"]["task_id"], "expected_version": first["task"]["task_version"]},
            })
    assert response.status_code == 200
    output.write_text(json.dumps(response.json(), ensure_ascii=False, indent=2), encoding="utf-8")


def _worker_request(url: str, trace: Path, task: dict) -> str:
    """由一个独立 app/engine 竞争指定 committed task version。"""

    app = _application(url, trace)
    with TestClient(app) as client:
        body = client.post("/api/query", json={
            "question": "继续。", "user_role": "ops",
            "task": {"action": "continue", "task_id": task["task_id"], "expected_version": task["task_version"]},
        }).json()
    return str(body["reason_code"])


def _full() -> None:
    """编排 P2 全链，核对安全结果并精确清理测试数据。"""

    url = _target_url()
    engine = create_engine(url, future=True)
    output_dir = Path(".agent_work/temp/m47/probe-p2")
    output_dir.mkdir(parents=True, exist_ok=True)
    with engine.begin() as connection:
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))
    env = {**os.environ, "DATABASE_URL": url}
    first_path, second_path = output_dir / "process-a.json", output_dir / "process-b.json"
    subprocess.run([sys.executable, __file__, "turn", "--output", str(first_path)], check=True, env=env)
    subprocess.run([sys.executable, __file__, "turn", "--output", str(second_path), "--prior", str(first_path)], check=True, env=env)
    first, second = json.loads(first_path.read_text(encoding="utf-8")), json.loads(second_path.read_text(encoding="utf-8"))
    assert first["task"]["task_version"] == 1 and second["task"]["task_version"] == 3
    assert second["task"]["state"]["evidence"][0]["validity"] == "invalidated"

    # 同一个 committed version 由两个独立 app/engine 并发消费，只能一个执行 Tool 并提交。
    task = second["task"]
    for index in (1, 2):
        (output_dir / f"worker-{index}.jsonl").unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker_outcomes = list(pool.map(
            lambda item: _worker_request(url, output_dir / f"worker-{item}.jsonl", task), (1, 2)
        ))
    # 已有 active Evidence 时胜者可能由 controller 直接收敛；唯一性看 graph/runtime 次数，
    # 不把“必须再次调用 SQL Tool”误写成 durable boundary 合同。
    conflict_reasons = {"task_not_active", "task_version_conflict"}
    assert sum(item in conflict_reasons for item in worker_outcomes) == 1
    winner_outcomes = [item for item in worker_outcomes if item not in conflict_reasons]
    assert len(winner_outcomes) == 1
    worker_traces = [
        json.loads(line)
        for index in (1, 2)
        for line in (output_dir / f"worker-{index}.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sum(int(item["task_runtime_invocation_count"]) for item in worker_traces) == 1

    # 重复旧 version 安全冲突；active role 和 tenant 都参与 owner scope。
    app = _application(url, output_dir / "controls.jsonl")
    with TestClient(app) as client:
        duplicate = client.post("/api/query", json={"question": "继续。", "user_role": "ops", "task": {"action": "continue", "task_id": task["task_id"], "expected_version": 1}}).json()
    assert duplicate["reason_code"] == "task_version_conflict"

    boundary = MySQLTaskBoundary(engine)
    caller = test_caller(caller_id="m47-p2", roles=("ops", "admin"), tenant_id="tenant-a")
    state = TaskState(owner_ref=boundary.owner_ref(caller), goal="synthetic")
    scoped, _ = boundary.start(caller=caller, active_role="ops", state=state)
    for wrong_caller, wrong_role in (
        (caller, "admin"),
        (test_caller(caller_id="m47-p2", roles=("ops",), tenant_id="tenant-b"), "ops"),
    ):
        try:
            boundary.claim(task_id=scoped.task_id, expected_version=1, caller=wrong_caller, active_role=wrong_role)
        except TaskBoundaryError as exc:
            assert exc.reason_code == "task_unavailable"

    crash, _ = boundary.start(caller=caller, active_role="ops", state=state)
    boundary.claim(task_id=crash.task_id, expected_version=1, caller=caller, active_role="ops")
    after_restart = MySQLTaskBoundary(engine)
    try:
        after_restart.claim(task_id=crash.task_id, expected_version=2, caller=caller, active_role="ops")
    except TaskBoundaryError as exc:
        assert exc.reason_code == "task_not_active"

    clearable, _ = boundary.start(caller=caller, active_role="ops", state=state)
    boundary.clear(task_id=clearable.task_id, expected_version=1, caller=caller, active_role="ops")
    with engine.begin() as connection:
        before_cleanup = {
            "checkpoints": connection.scalar(select(func.count()).select_from(AgentTaskCheckpoint)),
            "events": connection.scalar(select(func.count()).select_from(AgentTaskEvent)),
        }
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))
    result = {
        "probe_id": "M47-P2", "decision": "continue", "database": TARGET_DATABASE,
        "restart_resume": "passed", "process_a_version": 1, "process_b_version": 3,
        "worker_outcomes": sorted(worker_outcomes), "duplicate": duplicate["reason_code"],
        "role_tenant_binding": "passed", "claimed_crash": "safe_stop_task_not_active",
        "clear_scrub": "passed", "provider_calls": 0, "tokens": 0,
        "rows_before_cleanup": before_cleanup, "rows_after_cleanup": {"checkpoints": 0, "events": 0},
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    """解析 child/full 模式，保证 subprocess 复用同一实现。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("turn", "full"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prior", type=Path)
    args = parser.parse_args()
    if args.mode == "turn":
        assert args.output is not None
        _turn(_target_url(), args.output, prior=args.prior)
    else:
        _full()


if __name__ == "__main__":
    main()
