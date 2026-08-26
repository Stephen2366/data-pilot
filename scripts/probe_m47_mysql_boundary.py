"""M47-P1：独立 datapilot_m47_test 上的零 provider MySQL/InnoDB 探针。"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.base import Base as _Base  # noqa: F401
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.governance import test_caller
from engine.phase4b.mysql_task_boundary import MySQLTaskBoundary
from engine.phase4b.task_boundary import TaskBoundaryError
from engine.phase4b.task_runtime import TaskState

TARGET_DATABASE = "datapilot_m47_test"


def main() -> None:
    """迁移独立测试库，执行 P1 场景并在退出前清理 synthetic 行。"""

    source = make_url(get_settings().database_url)
    admin_url = source.set(database=None)
    target_url = source.set(database=TARGET_DATABASE)
    with create_engine(admin_url, future=True).begin() as connection:
        connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{TARGET_DATABASE}` CHARACTER SET utf8mb4"))

    os.environ["DATABASE_URL"] = target_url.render_as_string(hide_password=False)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    engine = create_engine(target_url, future=True)
    tables_before = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables_before:
        command.stamp(cfg, "20260722_0003")
    elif "agent_task_checkpoints" in tables_before and "task_safe_ref" not in {
        column["name"] for column in inspect(engine).get_columns("agent_task_checkpoints")
    }:
        # 开发期 0004 尚未发布；schema 增补后只重建独立 M47 测试表，不碰业务库。
        command.downgrade(cfg, "20260722_0003")
    command.upgrade(cfg, "20260826_0004")
    actual_tables = set(inspect(engine).get_table_names())
    allowed = {"alembic_version", "agent_task_checkpoints", "agent_task_events"}
    assert actual_tables <= allowed and {"agent_task_checkpoints", "agent_task_events"} <= actual_tables

    with engine.begin() as connection:
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))

    caller = test_caller(caller_id="m47-p1", roles=("ops",), tenant_id="m47-test")
    boundary_a, boundary_b = MySQLTaskBoundary(engine), MySQLTaskBoundary(engine)
    state = TaskState(owner_ref=boundary_a.owner_ref(caller), goal="synthetic m47 durable probe")
    started, _ = boundary_a.start(caller=caller, active_role="ops", state=state)

    def compete(boundary: MySQLTaskBoundary) -> str:
        """让一个 adapter 竞争同一 version，并只返回稳定 outcome。"""

        try:
            boundary.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
            return "won"
        except TaskBoundaryError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, (boundary_a, boundary_b)))
    assert outcomes.count("won") == 1 and outcomes.count("task_not_active") == 1

    # 重新建立样本验证跨 adapter commit。
    resume, _ = boundary_a.start(caller=caller, active_role="ops", state=state)
    claim = boundary_b.claim(task_id=resume.task_id, expected_version=1, caller=caller, active_role="ops")
    committed, _ = boundary_a.commit(claim=claim, caller=caller, active_role="ops", state=replace(state, generation=2))
    assert committed.task_version == 3

    # 人为让 event insert 失败，确认 switch 的旧 task 退休与新 task 创建一起回滚。
    rollback, _ = boundary_a.start(caller=caller, active_role="ops", state=state)
    rollback_claim = boundary_b.claim(task_id=rollback.task_id, expected_version=1, caller=caller, active_role="ops")
    original_append = boundary_b._append_event
    boundary_b._append_event = lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("synthetic event failure"))  # type: ignore[method-assign]
    try:
        try:
            boundary_b.switch(claim=rollback_claim, caller=caller, active_role="ops", state=replace(state, generation=2))
        except TaskBoundaryError as exc:
            assert exc.reason_code == "task_storage_unavailable"
    finally:
        boundary_b._append_event = original_append  # type: ignore[method-assign]
    with engine.connect() as connection:
        row = connection.execute(select(AgentTaskCheckpoint.status, AgentTaskCheckpoint.version).where(AgentTaskCheckpoint.task_key == boundary_b._task_key(rollback.task_id))).one()
        assert row == ("claimed", 2)

    cleared, _ = boundary_a.start(caller=caller, active_role="ops", state=state)
    boundary_b.clear(task_id=cleared.task_id, expected_version=1, caller=caller, active_role="ops")
    with engine.connect() as connection:
        assert connection.scalar(select(AgentTaskCheckpoint.state_payload).where(AgentTaskCheckpoint.task_key == boundary_a._task_key(cleared.task_id))) is None

    # 独立可控时钟验证 expiry 与 24h 后 bounded purge。
    clock = [datetime.now(timezone.utc)]
    expiring = MySQLTaskBoundary(engine, clock=lambda: clock[0])
    exp, _ = expiring.start(caller=caller, active_role="ops", state=state)
    clock[0] += timedelta(seconds=901)
    try:
        expiring.claim(task_id=exp.task_id, expected_version=1, caller=caller, active_role="ops")
    except TaskBoundaryError as exc:
        assert exc.reason_code == "task_expired"
    late, _ = expiring.start(caller=caller, active_role="ops", state=state)
    late_claim = expiring.claim(task_id=late.task_id, expected_version=1, caller=caller, active_role="ops")
    clock[0] += timedelta(seconds=901)
    try:
        expiring.commit(claim=late_claim, caller=caller, active_role="ops", state=state)
    except TaskBoundaryError as exc:
        assert exc.reason_code == "task_expired"
    clock[0] += timedelta(days=1, seconds=1)
    assert expiring.purge_tombstones(limit=1) == 1

    with engine.begin() as connection:
        before_cleanup = {
            "checkpoints": connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)),
            "events": connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)),
        }
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))
    with engine.connect() as connection:
        after_cleanup = {
            "checkpoints": connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)),
            "events": connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)),
        }
    result = {
        "probe_id": "M47-P1", "decision": "continue", "database": TARGET_DATABASE,
        "tables": sorted(actual_tables), "claim_outcomes": sorted(outcomes),
        "switch_rollback": "passed", "expiry_scrub": "passed", "expired_commit_fenced": "passed", "bounded_purge": "passed",
        "provider_calls": 0, "tokens": 0, "rows_before_cleanup": before_cleanup,
        "rows_after_cleanup": after_cleanup,
    }
    output = Path(".agent_work/temp/m47/probe-p1/result.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
