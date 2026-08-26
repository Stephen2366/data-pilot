"""M48-P1：独立 datapilot_m48_test 上的 Context/Compact 原子持久化探针。"""

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
from engine.phase4b.task_boundary import TaskBoundaryError, TaskBoundaryEvent
from engine.phase4b.task_context import TaskContextBuilder, TaskContextWindow
from engine.phase4b.task_runtime import TaskDelta, TaskState

TARGET_DATABASE = "datapilot_m48_test"
HEAD = "20260827_0005"


def _state(boundary: MySQLTaskBoundary, caller, generation: int = 1) -> TaskState:
    """构造不依赖业务表的 synthetic typed state。"""

    return TaskState(
        owner_ref=boundary.owner_ref(caller), generation=generation,
        goal="synthetic m48 context probe",
        constraints=(("metric", "net_refund_amount"), ("periods", ("2026-07",))),
        requirements=("sql:net_refund_amount:2026-07",), route="sql",
    )


def _append(window: TaskContextWindow, state: TaskState, ordinal: int, version_after: int) -> TaskContextWindow:
    """为 P1 形成真实入库的 bounded raw + typed turn。"""

    return TaskContextBuilder().append_committed_turn(
        window=window, question=f"synthetic m48 turn {ordinal}", version_after=version_after,
        delta=TaskDelta(category="continue", set_constraints=state.constraints, route="sql"),
        state=state, action_count=1, termination_reason="completed",
        budget_identity=f"budget:{ordinal}",
    )


def _event(window: TaskContextWindow, state: TaskState) -> TaskBoundaryEvent:
    """把 context 最后一条 typed turn 投影成 event v2。"""

    turn = window.uncovered_turns[-1]
    return TaskBoundaryEvent(
        delta_category=turn.delta_category, transition_identity=turn.transition_identity,
        action_count=turn.action_count, termination_reason=turn.termination_reason,
        turn_ordinal=turn.ordinal, state_identity=state.identity,
        constraint_keys=turn.constraint_keys, requirement_identities=turn.requirement_identities,
        active_evidence_identities=turn.active_evidence_identities,
        budget_identity=turn.budget_identity, context_identity=window.identity,
        compact_identity=window.compact.identity if window.compact else None,
        schema_version="phase4b-task-boundary-event-v2",
    )


def main() -> None:
    """迁移隔离库，执行 CAS/rollback/scrub/purge，并精确清理 synthetic 行。"""

    source = make_url(get_settings().database_url)
    if source.get_backend_name() != "mysql":
        raise RuntimeError("M48-P1 必须使用真实 MySQL URL")
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
    command.upgrade(cfg, HEAD)
    inspector = inspect(engine)
    required_columns = {
        "context_schema_version", "context_identity", "context_payload", "context_source_watermark",
    }
    actual_columns = {item["name"] for item in inspector.get_columns("agent_task_checkpoints")}
    assert required_columns <= actual_columns
    actual_tables = set(inspector.get_table_names())
    allowed = {"alembic_version", "agent_task_checkpoints", "agent_task_events"}
    assert actual_tables <= allowed and allowed <= actual_tables

    with engine.begin() as connection:
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))

    caller = test_caller(caller_id="m48-p1", roles=("ops",), tenant_id="m48-test")
    boundary_a, boundary_b = MySQLTaskBoundary(engine), MySQLTaskBoundary(engine)
    state = _state(boundary_a, caller)
    context = _append(TaskContextWindow.empty(), state, 1, 1)
    started, _ = boundary_a.start(
        caller=caller, active_role="ops", state=state, context=context, event=_event(context, state),
    )
    claim = boundary_a.claim(
        task_id=started.task_id, expected_version=1, caller=caller, active_role="ops",
    )
    next_state = replace(state, generation=2)
    next_context = _append(context, next_state, 2, 3)

    def compete(boundary: MySQLTaskBoundary) -> str:
        """两个 worker 使用同一 capability 竞争包含 context mutation 的 commit。"""

        try:
            boundary.commit(
                claim=claim, caller=caller, active_role="ops", state=next_state,
                context=next_context, event=_event(next_context, next_state),
            )
            return "won"
        except TaskBoundaryError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, (boundary_a, boundary_b)))
    assert outcomes.count("won") == 1 and outcomes.count("task_version_conflict") == 1
    resumed = boundary_b.claim(task_id=started.task_id, expected_version=3, caller=caller, active_role="ops")
    assert resumed.context == next_context and resumed.state == next_state

    # 事件写失败必须让 state/context/version 一起回滚。
    rollback_state = replace(next_state, generation=3)
    rollback_context = _append(next_context, rollback_state, 3, 5)
    original_append = boundary_b._append_event
    boundary_b._append_event = lambda *args, **kwargs: (_ for _ in ()).throw(SQLAlchemyError("synthetic event failure"))  # type: ignore[method-assign]
    try:
        try:
            boundary_b.commit(
                claim=resumed, caller=caller, active_role="ops", state=rollback_state,
                context=rollback_context, event=_event(rollback_context, rollback_state),
            )
        except TaskBoundaryError as exc:
            assert exc.reason_code == "task_storage_unavailable"
    finally:
        boundary_b._append_event = original_append  # type: ignore[method-assign]
    with engine.connect() as connection:
        row = connection.execute(select(
            AgentTaskCheckpoint.version, AgentTaskCheckpoint.status,
            AgentTaskCheckpoint.state_identity, AgentTaskCheckpoint.context_identity,
        ).where(AgentTaskCheckpoint.task_key == boundary_b._task_key(started.task_id))).one()
        assert row == (4, "claimed", next_state.identity, next_context.identity)

    # clear 立即 scrub state/context；另起 task 验证 expiry/purge。
    boundary_a.commit(
        claim=resumed, caller=caller, active_role="ops", state=next_state,
        context=next_context, terminal_status="cleared", event=_event(next_context, next_state),
    )
    with engine.connect() as connection:
        scrubbed = connection.execute(select(
            AgentTaskCheckpoint.state_payload, AgentTaskCheckpoint.context_payload,
            AgentTaskCheckpoint.context_identity,
        ).where(AgentTaskCheckpoint.task_key == boundary_a._task_key(started.task_id))).one()
        assert scrubbed == (None, None, None)

    clock = [datetime.now(timezone.utc)]
    expiring = MySQLTaskBoundary(engine, clock=lambda: clock[0])
    exp_state = _state(expiring, caller)
    exp_context = _append(TaskContextWindow.empty(), exp_state, 1, 1)
    exp, _ = expiring.start(caller=caller, active_role="ops", state=exp_state, context=exp_context, event=_event(exp_context, exp_state))
    clock[0] += timedelta(seconds=901)
    try:
        expiring.claim(task_id=exp.task_id, expected_version=1, caller=caller, active_role="ops")
    except TaskBoundaryError as exc:
        assert exc.reason_code == "task_expired"
    with engine.connect() as connection:
        expired = connection.execute(select(
            AgentTaskCheckpoint.state_payload, AgentTaskCheckpoint.context_payload,
        ).where(AgentTaskCheckpoint.task_key == expiring._task_key(exp.task_id))).one()
        assert expired == (None, None)
    clock[0] += timedelta(days=1, seconds=1)
    assert expiring.purge_tombstones(limit=1) == 1

    with engine.begin() as connection:
        before_cleanup = {
            "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
            "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
        }
        connection.execute(delete(AgentTaskEvent))
        connection.execute(delete(AgentTaskCheckpoint))
    with engine.connect() as connection:
        after_cleanup = {
            "checkpoints": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskCheckpoint.__table__)) or 0),
            "events": int(connection.scalar(select(text("count(*)")).select_from(AgentTaskEvent.__table__)) or 0),
        }
    assert after_cleanup == {"checkpoints": 0, "events": 0}

    # 在 clean synthetic state 上验证 0005 downgrade/upgrade 对称，再恢复 head 供 P2 使用。
    command.downgrade(cfg, "20260826_0004")
    downgraded_columns = {item["name"] for item in inspect(engine).get_columns("agent_task_checkpoints")}
    assert not required_columns & downgraded_columns
    command.upgrade(cfg, HEAD)
    restored_columns = {item["name"] for item in inspect(engine).get_columns("agent_task_checkpoints")}
    assert required_columns <= restored_columns

    result = {
        "probe_id": "M48-P1", "classification": "exploratory",
        "baseline_eligible": False, "decision": "continue", "database": TARGET_DATABASE,
        "migration_head": HEAD, "context_columns": sorted(required_columns),
        "commit_outcomes": sorted(outcomes), "atomic_context_rollback": "passed",
        "clear_scrub": "passed", "expiry_scrub": "passed", "bounded_purge": "passed",
        "downgrade_upgrade": "passed", "provider_calls": 0, "tokens": 0,
        "rows_before_cleanup": before_cleanup, "rows_after_cleanup": after_cleanup,
    }
    output = Path(".agent_work/temp/m48/probe-p1/result.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
