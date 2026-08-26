"""M47 A/B/C：B5 合同、codec 与 durable adapter 的确定性门。"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select

from app.db.base import Base
from app.models.agent_task_checkpoint import AgentTaskCheckpoint, AgentTaskEvent
from engine.governance import test_caller as build_test_caller
from engine.phase4b.b5_contracts import B5ContractError, load_b5_contract_bundle
from engine.phase4b.mysql_task_boundary import MySQLTaskBoundary
from engine.phase4b.task_boundary import TaskBoundaryError
from engine.phase4b.task_runtime import TaskEvidence, TaskState
from engine.phase4b.task_state_codec import TaskStateCodec, TaskStateCodecError


def _caller(name: str = "alice"):
    """构造 tenant 固定、身份可变的可信测试 caller。"""

    return build_test_caller(caller_id=name, roles=("ops",), tenant_id="tenant-a")


def _state(boundary, caller=None) -> TaskState:
    """构造含约束和 Evidence 的最小合法 TaskState v2。"""

    caller = caller or _caller()
    return TaskState(
        owner_ref=boundary.owner_ref(caller), goal="查询净退款", constraints=(("periods", ["2026-07"]),),
        evidence=(TaskEvidence(ref={"evidence_safe_ref": "ev:1"}, route="sql", requirement_identity="req:1"),),
    )


def _boundary(tmp_path, *, clock=None):
    """创建两个 M47 表的隔离 SQLite durable adapter。"""

    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'm47.db'}", future=True)
    Base.metadata.create_all(engine, tables=[AgentTaskCheckpoint.__table__, AgentTaskEvent.__table__])
    return MySQLTaskBoundary(engine, clock=clock), engine


def test_b5_contract_is_content_bound_and_closed_world(tmp_path):
    """未知根字段不能通过合同加载。"""

    bundle = load_b5_contract_bundle()
    assert bundle.payload["storage"]["product_backend"] == "mysql"
    payload = dict(bundle.payload)
    payload["surprise"] = True
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(B5ContractError, match="b5_contract_shape_invalid"):
        load_b5_contract_bundle(path)


def test_task_state_codec_strict_round_trip_and_forbidden_key():
    """合法 state 无损往返，嵌套敏感字段被拒绝。"""

    boundary = type("B", (), {"owner_ref": staticmethod(lambda caller: "owner")})()
    state = _state(boundary)
    codec = TaskStateCodec()
    assert codec.decode(codec.encode(state)) == state
    poisoned = codec.encode(state)
    poisoned["last_budget"] = {"raw_question": "secret"}
    with pytest.raises(TaskStateCodecError, match="task_schema_incompatible"):
        codec.decode(poisoned)


def test_durable_restart_resume_and_single_winner(tmp_path):
    """新 adapter 可恢复旧写入，且同 version 只有一个 claim。"""

    first, engine = _boundary(tmp_path)
    caller, state = _caller(), _state(first)
    started, _ = first.start(caller=caller, active_role="ops", state=state)
    second = MySQLTaskBoundary(engine)
    claim = second.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    assert claim.state == state and claim.task_version == 2
    with pytest.raises(TaskBoundaryError, match="task_not_active"):
        first.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    committed, _ = second.commit(claim=claim, caller=caller, active_role="ops", state=replace(state, generation=2))
    assert committed.task_version == 3


def test_wrong_owner_is_uniform_and_terminal_payload_is_scrubbed(tmp_path):
    """错误 owner 不可枚举，clear 后数据库 payload 为空。"""

    boundary, engine = _boundary(tmp_path)
    caller, state = _caller(), _state(boundary)
    started, _ = boundary.start(caller=caller, active_role="ops", state=state)
    with pytest.raises(TaskBoundaryError) as caught:
        boundary.claim(task_id=started.task_id, expected_version=1, caller=_caller("mallory"), active_role="ops")
    assert caught.value.reason_code == "task_unavailable"
    cleared, _ = boundary.clear(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    assert cleared.status == "cleared"
    with engine.connect() as connection:
        row = connection.execute(select(AgentTaskCheckpoint.state_payload, AgentTaskCheckpoint.purge_after_us)).one()
        assert row.state_payload is None and row.purge_after_us is not None
        assert connection.scalar(select(func.count()).select_from(AgentTaskEvent)) == 3


def test_expiry_scrubs_payload_and_purge_is_bounded(tmp_path):
    """过期访问立即擦除，保留期后按 limit 清理。"""

    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    clock = [now]
    boundary, engine = _boundary(tmp_path, clock=lambda: clock[0])
    caller, state = _caller(), _state(boundary)
    started, _ = boundary.start(caller=caller, active_role="ops", state=state)
    clock[0] += timedelta(seconds=901)
    with pytest.raises(TaskBoundaryError, match="task_expired"):
        boundary.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    with engine.connect() as connection:
        row = connection.execute(select(AgentTaskCheckpoint.status, AgentTaskCheckpoint.state_payload)).one()
        assert row == ("expired", None)
    clock[0] += timedelta(days=1, seconds=1)
    assert boundary.purge_tombstones(limit=1) == 1


def test_claimed_crash_is_scrubbed_by_bounded_maintenance(tmp_path):
    """无人继续访问的 claimed crash 也不会无限保存 payload。"""

    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    clock = [now]
    boundary, engine = _boundary(tmp_path, clock=lambda: clock[0])
    caller, state = _caller(), _state(boundary)
    started, _ = boundary.start(caller=caller, active_role="ops", state=state)
    boundary.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    clock[0] += timedelta(seconds=901)
    assert boundary.expire_stale(limit=1) == 1
    with engine.connect() as connection:
        row = connection.execute(select(AgentTaskCheckpoint.status, AgentTaskCheckpoint.state_payload)).one()
        assert row == ("expired", None)


def test_expired_claim_cannot_commit_after_ttl(tmp_path):
    """claim capability 不能越过 TTL 提交或复活状态。"""

    now = datetime(2026, 8, 26, tzinfo=timezone.utc)
    clock = [now]
    boundary, engine = _boundary(tmp_path, clock=lambda: clock[0])
    caller, state = _caller(), _state(boundary)
    started, _ = boundary.start(caller=caller, active_role="ops", state=state)
    claim = boundary.claim(task_id=started.task_id, expected_version=1, caller=caller, active_role="ops")
    clock[0] += timedelta(seconds=901)
    with pytest.raises(TaskBoundaryError, match="task_expired"):
        boundary.commit(claim=claim, caller=caller, active_role="ops", state=state)
    with engine.connect() as connection:
        row = connection.execute(select(AgentTaskCheckpoint.status, AgentTaskCheckpoint.state_payload)).one()
        assert row == ("expired", None)
