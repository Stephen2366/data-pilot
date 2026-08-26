"""M48-B：state/event/context 同一 claim transaction 与 adapter parity。"""

from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import create_engine, select, update

from app.db.base import Base
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.governance import test_caller as build_test_caller
from engine.phase4b.mysql_task_boundary import MySQLTaskBoundary
from engine.phase4b.task_boundary import TaskBoundary, TaskBoundaryError, TaskBoundaryEvent
from engine.phase4b.task_context import TaskContextBuilder, TaskContextWindow
from engine.phase4b.task_runtime import TaskDelta, TaskState


def _caller():
    return build_test_caller(caller_id="m48", roles=("ops",), tenant_id="tenant-m48")


def _state(boundary, generation: int = 1) -> TaskState:
    return TaskState(
        owner_ref=boundary.owner_ref(_caller()), generation=generation,
        goal="查询实际净退款金额",
        constraints=(("metric", "net_refund_amount"), ("periods", ("2026-07",))),
        requirements=("sql:net_refund_amount:2026-07",), route="sql",
    )


def _context(state: TaskState, *, version_after: int = 1) -> TaskContextWindow:
    return TaskContextBuilder().append_committed_turn(
        window=TaskContextWindow.empty(), question="查询 2026 年 7 月实际净退款金额。",
        version_after=version_after,
        delta=TaskDelta(category="start_task", goal=state.goal, set_constraints=state.constraints, route="sql"),
        state=state, action_count=1, termination_reason="completed", budget_identity="budget:1",
    )


def _event(context: TaskContextWindow, state: TaskState) -> TaskBoundaryEvent:
    turn = context.uncovered_turns[-1]
    return TaskBoundaryEvent(
        delta_category=turn.delta_category, transition_identity=turn.transition_identity,
        action_count=turn.action_count, termination_reason=turn.termination_reason,
        turn_ordinal=turn.ordinal, state_identity=state.identity,
        constraint_keys=turn.constraint_keys, requirement_identities=turn.requirement_identities,
        active_evidence_identities=turn.active_evidence_identities,
        budget_identity=turn.budget_identity, context_identity=context.identity,
        compact_identity=context.compact.identity if context.compact else None,
        schema_version="phase4b-task-boundary-event-v2",
    )


def _mysql(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'm48-boundary.db'}", future=True)
    Base.metadata.create_all(engine, tables=[AgentTaskCheckpoint.__table__, AgentTaskEvent.__table__])
    return MySQLTaskBoundary(engine), engine


@pytest.mark.parametrize("kind", ["memory", "mysql"])
def test_context_round_trip_and_claim_fencing_are_adapter_equivalent(tmp_path, kind: str) -> None:
    """两个 adapter 都通过同一 seam 返回 Context，并拒绝旧 claim 覆盖。"""

    boundary = TaskBoundary(ttl_seconds=900) if kind == "memory" else _mysql(tmp_path)[0]
    state = _state(boundary)
    context = _context(state)
    started, _ = boundary.start(caller=_caller(), active_role="ops", state=state, context=context, event=_event(context, state))
    claim = boundary.claim(task_id=started.task_id, expected_version=1, caller=_caller(), active_role="ops")
    assert claim.context == context
    next_state = replace(state, generation=2)
    next_context = TaskContextBuilder().append_committed_turn(
        window=context, question="再看 8 月。", version_after=3,
        delta=TaskDelta(category="modify_constraint", set_constraints=(("periods", ("2026-08",)),), route="sql"),
        state=next_state, action_count=1, termination_reason="completed", budget_identity="budget:2",
    )
    committed, _ = boundary.commit(
        claim=claim, caller=_caller(), active_role="ops", state=next_state,
        context=next_context, event=_event(next_context, next_state),
    )
    assert committed.context == next_context and committed.task_version == 3
    with pytest.raises(TaskBoundaryError, match="task_version_conflict"):
        boundary.commit(
            claim=claim, caller=_caller(), active_role="ops", state=next_state,
            context=context, event=_event(context, next_state),
        )


def test_mysql_restart_event_v2_and_terminal_scrub(tmp_path) -> None:
    """新 adapter 恢复 Context；event v2 可审计；clear 同事务擦除 state/context。"""

    first, engine = _mysql(tmp_path)
    state = _state(first)
    context = _context(state)
    started, _ = first.start(caller=_caller(), active_role="ops", state=state, context=context, event=_event(context, state))
    second = MySQLTaskBoundary(engine)
    claim = second.claim(task_id=started.task_id, expected_version=1, caller=_caller(), active_role="ops")
    assert claim.context == context
    second.commit(
        claim=claim, caller=_caller(), active_role="ops", state=state,
        context=context, terminal_status="cleared", event=_event(context, state),
    )
    with engine.connect() as connection:
        row = connection.execute(select(
            AgentTaskCheckpoint.state_payload, AgentTaskCheckpoint.context_payload,
            AgentTaskCheckpoint.context_identity, AgentTaskCheckpoint.context_source_watermark,
        )).one()
        assert row == (None, None, None, None)
        versions = list(connection.execute(select(AgentTaskEvent.event_schema_version)).scalars())
        assert versions == ["phase4b-task-boundary-event-v2", "phase4b-task-boundary-event-v1", "phase4b-task-boundary-event-v2"]


def test_legacy_null_context_is_explicitly_source_incomplete(tmp_path) -> None:
    """0004 active row不会被猜成拥有完整 typed 历史。"""

    boundary, engine = _mysql(tmp_path)
    state = _state(boundary)
    started, _ = boundary.start(caller=_caller(), active_role="ops", state=state)
    with engine.begin() as connection:
        connection.execute(update(AgentTaskCheckpoint).values(
            context_schema_version=None, context_identity=None,
            context_payload=None, context_source_watermark=None,
        ))
    claim = boundary.claim(task_id=started.task_id, expected_version=1, caller=_caller(), active_role="ops")
    assert claim.context is not None and claim.context.source_complete is False


def test_mysql_context_index_tamper_fails_closed_and_rolls_back_claim(tmp_path) -> None:
    """行级 identity 漂移不能绕过 payload hash，失败 claim 也不能留下 claimed 半状态。"""

    boundary, engine = _mysql(tmp_path)
    state = _state(boundary)
    context = _context(state)
    started, _ = boundary.start(
        caller=_caller(), active_role="ops", state=state, context=context,
        event=_event(context, state),
    )
    with engine.begin() as connection:
        connection.execute(update(AgentTaskCheckpoint).values(context_identity="0" * 64))
    with pytest.raises(TaskBoundaryError, match="task_compact_identity_mismatch"):
        boundary.claim(
            task_id=started.task_id, expected_version=1, caller=_caller(), active_role="ops",
        )
    with engine.connect() as connection:
        assert connection.execute(select(
            AgentTaskCheckpoint.version, AgentTaskCheckpoint.status,
        )).one() == (1, "active")
