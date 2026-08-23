"""M43-C owner/version/TTL/claim/clear 的安全边界测试。"""

from datetime import datetime, timedelta, timezone

import pytest

from engine.governance import test_caller as make_caller
from engine.phase4b.task_boundary import TaskBoundary, TaskBoundaryError
from engine.phase4b.task_runtime import TaskState


def test_owner_and_missing_are_indistinguishable_and_claim_is_single_use() -> None:
    owner = make_caller(caller_id="owner", roles={"ops"})
    other = make_caller(caller_id="other", roles={"ops"})
    boundary = TaskBoundary()
    task, _ = boundary.start(caller=owner, state=TaskState(owner_ref=boundary.owner_ref(owner), goal="g"))
    for task_id, caller in ((task.task_id, other), ("missing", owner)):
        with pytest.raises(TaskBoundaryError) as caught:
            boundary.claim(task_id=task_id, expected_version=1, caller=caller)
        assert caught.value.reason_code == "task_unavailable"
    claim = boundary.claim(task_id=task.task_id, expected_version=1, caller=owner)
    with pytest.raises(TaskBoundaryError, match="task_not_active"):
        boundary.claim(task_id=task.task_id, expected_version=1, caller=owner)
    committed, _ = boundary.commit(claim=claim, caller=owner, state=claim.state)
    assert committed.task_version == 3


def test_ttl_and_clear_are_explicitly_process_local() -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    caller = make_caller(caller_id="owner", roles={"ops"})
    boundary = TaskBoundary(ttl_seconds=1, clock=lambda: now)
    task, _ = boundary.start(caller=caller, state=TaskState(owner_ref=boundary.owner_ref(caller), goal="g"))
    assert boundary.runtime_identity["durability"] == "process_local_non_durable"
    expired = TaskBoundary(ttl_seconds=1, clock=lambda: now + timedelta(seconds=2))
    expired._items = boundary._items  # 测试同一 adapter 的时钟推进，不作为公开接口使用。
    with pytest.raises(TaskBoundaryError, match="task_expired"):
        expired.claim(task_id=task.task_id, expected_version=1, caller=caller)
    cleared, fact = boundary.clear(task_id=task.task_id, expected_version=1, caller=caller)
    assert cleared.status == "cleared" and fact.action == "cleared"


def test_switch_retires_old_and_creates_new_in_one_boundary_operation() -> None:
    caller = make_caller(caller_id="owner", roles={"ops"})
    boundary = TaskBoundary()
    first, _ = boundary.start(caller=caller, state=TaskState(owner_ref=boundary.owner_ref(caller), goal="old"))
    claim = boundary.claim(task_id=first.task_id, expected_version=1, caller=caller)
    new, fact = boundary.switch(claim=claim, caller=caller, state=TaskState(owner_ref=boundary.owner_ref(caller), goal="new"))
    assert new.task_id != first.task_id and new.task_version == 1 and fact.action == "switched"
    with pytest.raises(TaskBoundaryError, match="task_not_active"):
        boundary.claim(task_id=first.task_id, expected_version=3, caller=caller)
