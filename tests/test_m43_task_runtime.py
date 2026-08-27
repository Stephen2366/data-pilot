"""M43-B/D TaskDelta、证据失效与节点上下文合同。"""

from engine.phase4b.task_runtime import TaskEvidence, TaskState, apply_delta, project_node_contexts, understand_turn


def test_canonical_t1_t2_invalidates_old_sql_and_preserves_generic_state() -> None:
    owner = "owner-safe-ref"
    first = understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None)
    state, _ = apply_delta(None, first, owner_ref=owner)
    state = TaskState(**{**state.__dict__, "evidence": (TaskEvidence({"evidence_kind": "sql", "evidence_id": "safe"}, "sql", state.requirements[-1]),)})

    second = understand_turn("改成 8 月，并和 7 月比较。", action="continue", previous=state)
    updated, transition = apply_delta(state, second, owner_ref=owner)

    assert second.category == "modify_constraint"
    assert dict(updated.constraints) == {"comparison": True, "metric": "net_refund_amount", "periods": ("2026-07", "2026-08")}
    assert updated.evidence[0].validity == "invalidated"
    assert transition.invalidated_evidence_count == 1
    assert not {"refund", "month", "channel"} & set(updated.safe_projection())


def test_complete_explicit_restatement_replaces_primary_requirement_without_magic_change_words() -> None:
    """用户把主问题完整说清楚时，不应因为没说“改成”而追加第二个主任务。"""

    owner = "owner-safe-ref"
    first = understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None)
    state, _ = apply_delta(None, first, owner_ref=owner)
    state = TaskState(**{
        **state.__dict__,
        "evidence": (
            TaskEvidence(
                {"evidence_kind": "sql", "evidence_id": "safe"},
                "sql",
                state.requirements[-1],
            ),
        ),
    })

    delta = understand_turn(
        "比较 2026 年 7 月和 8 月实际净退款金额，并计算差额和变化率。",
        action="continue",
        previous=state,
    )
    updated, transition = apply_delta(state, delta, owner_ref=owner)

    assert delta.category == "modify_constraint"
    assert updated.requirements == ("sql:net_refund_amount:2026-07,2026-08",)
    assert [item.purpose for item in updated.evidence_requirements] == ["metric_comparison"]
    assert updated.evidence[0].validity == "invalidated"
    assert transition.invalidated_evidence_count == 1


def test_explicit_additional_evidence_wording_remains_additive() -> None:
    """完整字段不等于永远替换；明确“再查证”仍要保留已有 requirement。"""

    previous, _ = apply_delta(
        None,
        understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None),
        owner_ref="owner",
    )
    delta = understand_turn(
        "再查证 2026 年 8 月实际净退款金额。",
        action="continue",
        previous=previous,
    )
    updated, _ = apply_delta(previous, delta, owner_ref="owner")

    assert delta.category == "add_evidence_requirement"
    assert updated.requirements == (
        "sql:net_refund_amount:2026-07",
        "sql:net_refund_amount:2026-08",
    )


def test_ask_existing_result_is_empty_delta_and_never_reverts_current_requirements() -> None:
    """解释旧结果只读取 digest，不应凭旧约束重新制造 SQL requirement。"""

    previous, _ = apply_delta(
        None,
        understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None),
        owner_ref="owner",
    )
    corrected, _ = apply_delta(
        previous,
        understand_turn("更正为按渠道比较 2026 年 7 月和 8 月。", action="continue", previous=previous),
        owner_ref="owner",
    )
    delta = understand_turn("解释这个结果。", action="continue", previous=corrected)
    resumed, _ = apply_delta(corrected, delta, owner_ref="owner")

    assert delta.category == "ask_about_existing_result"
    assert delta.add_requirements == delta.evidence_requirements == ()
    assert dict(delta.set_constraints) == {}
    assert resumed.requirements == corrected.requirements
    assert resumed.route == corrected.route


def test_ambiguous_delta_clarifies_without_inventing_period_and_context_is_bounded() -> None:
    previous, _ = apply_delta(None, understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None), owner_ref="owner")
    delta = understand_turn("改成另一个月。", action="continue", previous=previous)
    # “另一个月”不能沿用旧 period 假装已经理解。
    assert delta.pending_questions == ("periods",)
    state, _ = apply_delta(previous, delta, owner_ref="owner")
    contexts = project_node_contexts(question="改成另一个月。", state=state, delta=delta)
    assert state.status == "clarification_required"
    assert {item.purpose for item in contexts} == {"turn_understanding", "route_execution", "sql", "controller_response"}
    assert all(len(item.payload) <= item.field_budget for item in contexts)
    assert all("rows" not in item.payload and "answer" not in item.payload for item in contexts)


def test_switch_starts_independent_state_without_previous_constraints_or_evidence() -> None:
    previous, _ = apply_delta(None, understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None), owner_ref="owner")
    previous = TaskState(**{**previous.__dict__, "evidence": (TaskEvidence({"evidence_kind": "sql", "evidence_id": "old"}, "sql", previous.requirements[-1]),)})
    delta = understand_turn("换个问题，查询 2026 年 8 月实际净退款金额。", action="switch", previous=previous)
    switched, transition = apply_delta(previous, delta, owner_ref="owner")
    assert switched.generation == 1 and switched.evidence == ()
    assert dict(switched.constraints)["periods"] == ("2026-08",)
    assert switched.requirements == ("sql:net_refund_amount:2026-08",)
    assert transition.invalidated_evidence_count == 1


def test_cancel_is_envelope_control_and_invalidates_active_evidence() -> None:
    previous, _ = apply_delta(None, understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None), owner_ref="owner")
    previous = TaskState(**{**previous.__dict__, "evidence": (TaskEvidence({"evidence_kind": "sql", "evidence_id": "old"}, "sql", previous.requirements[-1]),)})
    # start 信封里的取消文本不能越权执行 lifecycle cancel，只会作为不完整新任务保守澄清。
    text_only = understand_turn("取消任务。", action="start", previous=None)
    assert text_only.category == "start_task" and text_only.pending_questions
    cancelled, transition = apply_delta(previous, understand_turn("取消任务。", action="cancel", previous=previous), owner_ref="owner")
    assert cancelled.status == "cancelled"
    assert cancelled.evidence[0].validity == "invalidated"
    assert transition.invalidated_evidence_count == 1
