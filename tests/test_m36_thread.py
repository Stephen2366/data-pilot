"""M36 checkpoint/Context 合同测试：只从深 module interface 观察行为。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor

import pytest

from engine.governance import authenticated_caller, demo_caller
from engine.harness.contracts import HarnessRequest
from engine.harness.router import DeterministicRouter
from engine.harness.thread import ThreadCheckpointManager, ThreadLifecycleError


class FakeClock:
    """可手动推进的 timezone-aware clock，TTL 测试无需真实 sleep。"""

    def __init__(self) -> None:
        self.value = datetime(2026, 8, 16, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        """返回当前 fixture 时间。"""

        return self.value

    def advance(self, *, seconds: int) -> None:
        """确定性推进时间。"""

        self.value += timedelta(seconds=seconds)


def _request(question: str, *, caller_id: str = "owner", role: str = "ops", run_id: str = "turn-1") -> HarnessRequest:
    """构造一个可信 Harness 请求。"""

    caller = demo_caller(caller_id=caller_id, roles=(role,))
    return HarnessRequest(question=question, run_id=run_id, caller=caller, active_sql_role=role)


def _pending(manager: ThreadCheckpointManager, question: str = "这个怎么处理？"):
    """通过真实 deterministic Router 创建 pending checkpoint。"""

    request = _request(question)
    decision = DeterministicRouter().decide(request)
    assert decision.clarification_spec is not None
    projection, _fact = manager.create_pending(request, decision.clarification_spec)
    return request, projection


def test_subject_answers_build_minimal_rag_task_without_exposing_checkpoint() -> None:
    """缺主体只消费 subject 字段，并把它变成可由现有 Router 判断的当前任务。"""

    manager = ThreadCheckpointManager()
    request, pending = _pending(manager)

    claim = manager.claim_resume(
        thread_id=pending.thread_id,
        expected_version=pending.checkpoint_version,
        caller=request.caller,
        active_sql_role="ops",
        answers={"subject": "退款政策"},
        run_id="turn-2",
    )

    assert claim.request.question == "关于退款政策，应该如何处理？"
    assert DeterministicRouter().decide(claim.request).route == "rag"
    assert claim.lifecycle.context_ref and "退款政策" not in claim.lifecycle.context_ref
    assert claim.projection.status == "claimed"
    assert claim.projection.clarification is None


def test_analytics_answers_preserve_original_task_and_route_to_sql() -> None:
    """退款分析补齐时间/维度后走 SQL，不把它误判成政策 RAG。"""

    manager = ThreadCheckpointManager()
    request, pending = _pending(manager, "退款情况怎么样？")

    claim = manager.claim_resume(
        thread_id=pending.thread_id,
        expected_version=1,
        caller=request.caller,
        active_sql_role="ops",
        answers={"time_range": "2026年6月", "group_by": "渠道"},
        run_id="turn-2",
    )

    assert "退款情况怎么样" in claim.request.question
    assert "2026年6月" in claim.request.question and "按渠道统计" in claim.request.question
    assert DeterministicRouter().decide(claim.request).route == "sql"


def test_invalid_answers_do_not_consume_pending_version() -> None:
    """缺字段/额外字段先失败，修正后仍可用同一 version 恢复。"""

    manager = ThreadCheckpointManager()
    request, pending = _pending(manager, "退款情况怎么样？")

    with pytest.raises(ThreadLifecycleError, match="字段不闭合") as captured:
        manager.claim_resume(
            thread_id=pending.thread_id,
            expected_version=1,
            caller=request.caller,
            active_sql_role="ops",
            answers={"time_range": "2026年6月"},
            run_id="bad-turn",
        )
    assert captured.value.reason_code == "clarification_answers_invalid"

    claim = manager.claim_resume(
        thread_id=pending.thread_id,
        expected_version=1,
        caller=request.caller,
        active_sql_role="ops",
        answers={"time_range": "2026年6月", "group_by": "渠道"},
        run_id="good-turn",
    )
    assert claim.projection.checkpoint_version == 2


def test_owner_missing_expiry_clear_and_state_version_fail_before_resume() -> None:
    """owner/lifecycle 反例都有稳定 reason，且错误 caller 看不到 thread 细节。"""

    clock = FakeClock()
    manager = ThreadCheckpointManager(ttl_seconds=30, clock=clock)
    request, pending = _pending(manager)
    intruder = demo_caller(caller_id="intruder", roles=("ops",))

    with pytest.raises(ThreadLifecycleError) as wrong_owner:
        manager.claim_resume(
            thread_id=pending.thread_id,
            expected_version=1,
            caller=intruder,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="intruder",
        )
    assert (wrong_owner.value.reason_code, wrong_owner.value.safety_status) == (
        "conversation_unavailable",
        "blocked",
    )

    clock.advance(seconds=31)
    with pytest.raises(ThreadLifecycleError) as expired:
        manager.claim_resume(
            thread_id=pending.thread_id,
            expected_version=1,
            caller=request.caller,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="expired",
        )
    assert expired.value.reason_code == "thread_expired"

    fresh = ThreadCheckpointManager()
    fresh_request, fresh_pending = _pending(fresh)
    cleared, _fact = fresh.clear(
        thread_id=fresh_pending.thread_id,
        expected_version=1,
        caller=fresh_request.caller,
    )
    assert (cleared.status, cleared.checkpoint_version) == ("cleared", 2)
    with pytest.raises(ThreadLifecycleError) as cleared_resume:
        fresh.claim_resume(
            thread_id=fresh_pending.thread_id,
            expected_version=2,
            caller=fresh_request.caller,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="cleared",
        )
    assert cleared_resume.value.reason_code == "thread_cleared"

    incompatible = ThreadCheckpointManager(accepted_state_version="m36-thread-v2")
    incompatible_request, incompatible_pending = _pending(incompatible)
    with pytest.raises(ThreadLifecycleError) as version_error:
        incompatible.claim_resume(
            thread_id=incompatible_pending.thread_id,
            expected_version=1,
            caller=incompatible_request.caller,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="incompatible",
        )
    assert version_error.value.reason_code == "state_version_incompatible"

    restarted = ThreadCheckpointManager()
    with pytest.raises(ThreadLifecycleError) as lost:
        restarted.claim_resume(
            thread_id=fresh_pending.thread_id,
            expected_version=1,
            caller=fresh_request.caller,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="restart-lost",
        )
    assert (lost.value.reason_code, lost.value.safety_status) == ("conversation_unavailable", "blocked")


def test_same_authenticated_identity_in_another_tenant_cannot_resume() -> None:
    """audit identity 相同也不能跨 tenant 消费 checkpoint。"""

    manager = ThreadCheckpointManager()
    tenant_a = authenticated_caller(
        caller_id="shared-user", roles=("ops",), identity_source="oidc", tenant_id="tenant-a"
    )
    tenant_b = authenticated_caller(
        caller_id="shared-user", roles=("ops",), identity_source="oidc", tenant_id="tenant-b"
    )
    request = HarnessRequest(
        question="这个怎么处理？", run_id="tenant-a-1", caller=tenant_a, active_sql_role="ops"
    )
    decision = DeterministicRouter().decide(request)
    assert decision.clarification_spec is not None
    pending, _fact = manager.create_pending(request, decision.clarification_spec)

    with pytest.raises(ThreadLifecycleError) as cross_tenant:
        manager.claim_resume(
            thread_id=pending.thread_id,
            expected_version=1,
            caller=tenant_b,
            active_sql_role="ops",
            answers={"subject": "退款政策"},
            run_id="tenant-b-1",
        )

    assert (cross_tenant.value.reason_code, cross_tenant.value.safety_status) == (
        "conversation_unavailable",
        "blocked",
    )


def test_same_expected_version_has_exactly_one_concurrent_claim() -> None:
    """compare-and-set 门禁保证并发请求只有一个取得后续 Tool 执行权。"""

    manager = ThreadCheckpointManager()
    request, pending = _pending(manager)
    barrier = Barrier(2)

    def claim(index: int) -> str:
        """让两个线程同时越过 barrier，再竞争 manager 内的原子 claim。"""

        barrier.wait()
        try:
            manager.claim_resume(
                thread_id=pending.thread_id,
                expected_version=1,
                caller=request.caller,
                active_sql_role="ops",
                answers={"subject": "退款政策"},
                run_id=f"concurrent-{index}",
            )
            return "claimed"
        except ThreadLifecycleError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(claim, (1, 2)))

    assert outcomes == ["claimed", "thread_already_resumed"]


def test_unknown_thread_reason_is_rejected_by_closed_world_registry() -> None:
    """新增 lifecycle 路径不能绕过 reason registry 临时造字符串。"""

    with pytest.raises(ValueError, match="未登记"):
        ThreadLifecycleError("invented_reason", "internal detail")
