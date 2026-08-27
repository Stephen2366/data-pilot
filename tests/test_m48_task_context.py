"""M48-B/C：Context codec、Compact、trigger 与 node privacy 的确定性门。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.phase4b.loop_contracts import AgentNodeContext
from engine.phase4b.task_context import (
    RawUserTurn,
    TypedTurnFact,
    TaskContextBuilder,
    TaskContextCodec,
    TaskContextError,
    TaskContextWindow,
    TaskResultDigest,
)
from engine.phase4b.task_runtime import TaskDelta, TaskEvidence, TaskState, apply_delta, understand_turn
from engine.phase4b.task_state_codec import TaskStateCodec


def _state(generation: int = 1) -> TaskState:
    return TaskState(
        owner_ref="owner", generation=generation, goal="查询实际净退款金额",
        constraints=(("metric", "net_refund_amount"), ("periods", ("2026-07", "2026-08"))),
        requirements=("sql:net_refund_amount:2026-07,2026-08",), route="sql",
        evidence=(TaskEvidence(
            ref={"evidence_id": "sql:120000:180000", "amounts": [120000, 180000, 60000], "rate": "50%"},
            route="sql", requirement_identity="sql:net_refund_amount:2026-07,2026-08",
        ),),
    )


def _delta() -> TaskDelta:
    return TaskDelta(
        category="continue", set_constraints=(("metric", "net_refund_amount"),),
        add_requirements=("sql:net_refund_amount:2026-07,2026-08",), route="sql",
    )


def _append(builder: TaskContextBuilder, window: TaskContextWindow, count: int) -> TaskContextWindow:
    for ordinal in range(1, count + 1):
        state = _state(ordinal)
        window = builder.append_committed_turn(
            window=window, question=f"第 {ordinal} 轮，金额不要取绝对值。", version_after=ordinal * 2 - 1,
            delta=_delta(), state=state, action_count=1, termination_reason="completed",
            budget_identity=f"budget:{ordinal}",
        )
    return window


def test_context_codec_round_trip_and_raw_is_not_public() -> None:
    """私有 recent text 可恢复，但 API/Trace 安全投影不含原文。"""

    builder = TaskContextBuilder()
    window = _append(builder, TaskContextWindow.empty(), 2)
    restored = TaskContextCodec().decode(TaskContextCodec().encode(window))
    assert restored == window
    safe = restored.safe_projection()
    assert "金额不要取绝对值" not in str(safe)
    assert safe["recent_raw_turn_count"] == 2


def test_result_digest_round_trips_and_survives_compact_without_raw_tool_payload() -> None:
    """M49 C：只保存有界回答摘要，Compact 后仍可由新 worker 读取。"""

    digest = TaskResultDigest(
        route="hybrid", answer_status="complete",
        summary_text="7 月和 8 月已按渠道比较，并核验退款政策。",
        evidence_ids=("sql-evidence", "doc-evidence"),
    )
    builder = TaskContextBuilder()
    window = builder.append_committed_turn(
        window=TaskContextWindow.empty(), question="原问题", version_after=1,
        delta=_delta(), state=_state(), action_count=2, termination_reason="answer_ready",
        budget_identity="budget", result_digest=digest,
    )
    restored = TaskContextCodec().decode(TaskContextCodec().encode(window))
    assert restored.latest_result_digest == digest
    assert "sql_rows" not in str(TaskContextCodec().encode(restored))

    five = window
    for ordinal in range(2, 6):
        five = builder.append_committed_turn(
            window=five, question=f"第 {ordinal} 轮", version_after=ordinal * 2 - 1,
            delta=_delta(), state=_state(ordinal), action_count=1,
            termination_reason="answer_ready", budget_identity=f"budget:{ordinal}",
        )
    prepared, decision = builder.prepare(
        window=five, state=_state(5),
        candidate_contexts=(AgentNodeContext("decision", ("state",), {}, (), 0, 128),),
    )
    assert decision.outcome == "triggered_and_committed"
    assert prepared.latest_result_digest == digest
    assert prepared.compact is not None and prepared.compact.result_digest == digest


def test_result_digest_is_bounded() -> None:
    """摘要文本和 Evidence ID 数量任一越界都必须在落库前拒绝。"""

    with pytest.raises(TaskContextError, match="task_context_payload_too_large"):
        TaskResultDigest(route="sql", answer_status="complete", summary_text="数" * 3000)


def test_task_state_v2_normalizes_json_array_constraints_across_restart() -> None:
    """M48-P1 回归：tuple periods 不能经 JSON restart 漂成 list。"""

    state = TaskState(owner_ref="owner", constraints=(("periods", ["2026-07", "2026-08"]),))
    restored = TaskStateCodec().decode(TaskStateCodec().encode(state))
    assert state == restored
    assert dict(restored.constraints)["periods"] == ("2026-07", "2026-08")


def test_raw_turn_utf8_limit_and_forbidden_key_fail_closed() -> None:
    """中文按 UTF-8 bytes 限制，敏感嵌套 key 不能进入 context。"""

    with pytest.raises(TaskContextError, match="task_context_payload_too_large"):
        RawUserTurn(1, 1, "数" * 683)
    window = _append(TaskContextBuilder(), TaskContextWindow.empty(), 1)
    poisoned = TaskContextCodec().encode(window)
    poisoned["compact"] = {"prompt": "secret"}
    with pytest.raises(TaskContextError, match="task_context_schema_incompatible"):
        TaskContextCodec().decode(poisoned)


def test_context_rejects_turn_gap_even_when_attacker_can_recompute_outer_identity() -> None:
    """uncovered ordinal 必须紧接 Compact/source watermark，不能只验证“有序且末项相等”。"""

    turn = TypedTurnFact(
        ordinal=2, version_after=3, delta_category="continue", transition_identity="transition",
        state_identity="state", constraint_keys=(), requirement_identities=(),
        active_evidence_identities=(), action_count=0, termination_reason="answer_ready",
        budget_identity="budget",
    )
    with pytest.raises(TaskContextError, match="task_context_schema_incompatible"):
        TaskContextWindow(
            uncovered_turns=(turn,), committed_turns_since_compact=1, source_watermark=2,
        )


def test_five_turn_trigger_builds_deterministic_exact_compact() -> None:
    """第六个 accepted turn 前按 5-turn 门触发，金额/月份/否定不被自由总结。"""

    builder = TaskContextBuilder()
    window = _append(builder, TaskContextWindow.empty(), 5)
    state = _state(5)
    candidate = AgentNodeContext("decision", (state.identity,), {"goal": state.goal}, ("goal",), 1, 128)
    prepared, decision = builder.prepare(window=window, state=state, candidate_contexts=(candidate,))
    assert decision.outcome == "triggered_and_committed"
    assert decision.trigger == "committed_turns"
    assert prepared.compact is not None
    assert prepared.compact.high_risk_references["constraints_exact"]["periods"] == ("2026-07", "2026-08")
    assert prepared.compact.high_risk_references["evidence_refs_exact"][0]["amounts"] == [120000, 180000, 60000]
    assert prepared.compact.identity == builder.prepare(window=window, state=state, candidate_contexts=(candidate,))[0].compact.identity
    assert prepared.uncovered_turns == () and prepared.committed_turns_since_compact == 0


def test_budget_trigger_and_source_incomplete_are_closed_world() -> None:
    """75% 预算门可独立触发；legacy source 不完整时禁止猜 Compact。"""

    builder = TaskContextBuilder(committed_turns=99, candidate_budget_ratio=0.75)
    window = _append(builder, TaskContextWindow.empty(), 1)
    large = AgentNodeContext("decision", ("state",), {"value": "x" * 300}, ("value",), 1, 100)
    prepared, decision = builder.prepare(window=window, state=_state(), candidate_contexts=(large,))
    assert decision.trigger == "candidate_node_budget" and prepared.compact is not None
    legacy = _append(builder, TaskContextWindow.legacy_incomplete(), 1)
    force = TaskContextBuilder(committed_turns=1)
    with pytest.raises(TaskContextError, match="task_compact_source_incomplete"):
        force.prepare(window=legacy, state=_state(), candidate_contexts=())


def test_compact_build_failure_keeps_safe_uncompacted_source() -> None:
    """候选构建失败时不删 source；原 window 可 strict 保存才允许显式 fallback。"""

    class FailingBuilder(TaskContextBuilder):
        @staticmethod
        def _build_compact(*, state, window, trigger):  # type: ignore[no-untyped-def]
            raise TaskContextError("task_evidence_revalidation_failed", "synthetic fault")

    builder = FailingBuilder(committed_turns=1)
    window = _append(builder, TaskContextWindow.empty(), 1)
    prepared, decision = builder.prepare(window=window, state=_state(), candidate_contexts=())
    assert prepared == window
    assert decision.outcome == "fallback_uncompacted"
    assert decision.reason_code == "task_compact_fallback_uncompacted"
    assert decision.context_identity_before == decision.context_identity_after == window.identity


def test_node_context_builder_redacts_current_and_recent_raw() -> None:
    """Turn 节点实际收到 recent raw，但公开投影只留下不可逆 fingerprint。"""

    builder = TaskContextBuilder()
    window = _append(builder, TaskContextWindow.empty(), 2)
    contexts = builder.project_node_contexts(
        question="解释这个结果", state=_state(), delta=_delta(),
        prior_state_identity="state:old", window=window,
    )
    turn = contexts[0]
    assert turn.payload["recent_user_turns"]
    safe = turn.safe_projection()
    assert "解释这个结果" not in str(safe)
    assert "金额不要取绝对值" not in str(safe)
    assert safe["private_fields"] == ["question", "recent_user_turns"]
    assert all("recent_user_turns" not in item.payload for item in contexts[1:])


def test_pre_post_compact_next_turn_has_same_typed_behavior() -> None:
    """同一 next turn 在 compact 前后产生相同 Delta/State/route/Evidence validity。"""

    builder = TaskContextBuilder()
    state = _state(5)
    before = _append(builder, TaskContextWindow.empty(), 5)
    candidate = builder.project_node_contexts(
        question="继续解释。", state=state, delta=_delta(),
        prior_state_identity=state.identity, window=before,
    )
    after, decision = builder.prepare(window=before, state=state, candidate_contexts=candidate)
    assert decision.outcome == "triggered_and_committed"

    question = "更正为按渠道比较 2026 年 7 月和 8 月。"
    delta_before = understand_turn(question, action="continue", previous=state)
    delta_after = understand_turn(question, action="continue", previous=state)
    state_before, transition_before = apply_delta(state, delta_before, owner_ref=state.owner_ref)
    state_after, transition_after = apply_delta(state, delta_after, owner_ref=state.owner_ref)
    assert delta_before == delta_after
    assert state_before == state_after
    assert transition_before == transition_after
    assert state_before.route == state_after.route == "sql"
    assert [item.validity for item in state_before.evidence] == [item.validity for item in state_after.evidence]
    # Context 载体 identity 会变，但业务节点 allowlist 中的 typed state 输入必须等价。
    before_route = builder.project_node_contexts(
        question=question, state=state_before, delta=delta_before,
        prior_state_identity=state.identity, window=before,
    )[1].payload
    after_route = builder.project_node_contexts(
        question=question, state=state_after, delta=delta_after,
        prior_state_identity=state.identity, window=after,
    )[1].payload
    for key in ("goal", "constraints", "requirements", "route"):
        assert before_route[key] == after_route[key]
