"""生成 M43/B1 deterministic rehearsal 与 Agent Scenario v2 artifact。

运行方式：在项目根目录执行 ``python -m scripts.rehearse_m43_b1``。它不调用 LLM、embedding、数据库或网络，只复核
合同、TaskState 转换、Evidence invalidation、节点上下文和冻结 oracle。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from engine.phase4b.b1_contracts import load_b1_contract_bundle
from engine.phase4b.task_runtime import NodeContext, TaskDelta, TaskState, apply_delta, attach_evidence, project_node_contexts, understand_turn
from eval.agent_scenario_v2_contracts import AgentTaskTurnFact, build_agent_scenario_v2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "eval" / "reports" / "m43"


def _lifecycle(action: str, state_identity: str, *, version_before: int | None, version_after: int) -> dict[str, object]:
    """形成与 runtime ``TaskLifecycleFact`` 相同的 closed-world rehearsal 投影。"""

    return {
        "task_safe_ref": f"task:rehearsal-{action}",
        "action": action,
        "reason_code": f"task_{action}",
        "version_before": version_before,
        "version_after": version_after,
        "state_identity": state_identity,
        "previous_task_safe_ref": "task:rehearsal-old" if action == "switched" else None,
    }


def _contexts(
    question: str,
    before_execution: TaskState,
    after_execution: TaskState,
    delta: TaskDelta,
    prior: str | None,
) -> tuple[NodeContext, ...]:
    """与 task turn 一致：前三个节点取执行前输入，controller 取执行后 Evidence。"""

    before = project_node_contexts(question=question, state=before_execution, delta=delta, prior_state_identity=prior)
    after = project_node_contexts(question=question, state=after_execution, delta=delta, prior_state_identity=prior)
    return (*before[:3], after[3])


def _run() -> tuple[dict[str, object], dict[str, object]]:
    bundle = load_b1_contract_bundle()
    owner = "rehearsal-owner-safe-ref"
    facts: list[AgentTaskTurnFact] = []

    first_delta = understand_turn("查询 2026 年 7 月实际净退款金额。", action="start", previous=None)
    first, first_transition = apply_delta(None, first_delta, owner_ref=owner)
    first_pre = first
    first = attach_evidence(first, ({"evidence_kind": "sql", "evidence_id": "m43-t1", "result_fingerprint": "oracle-july-120000"},))
    first_transition = replace(first_transition, after_identity=first.identity, changed_fields=(*first_transition.changed_fields, "evidence"))
    first_contexts = _contexts("查询 2026 年 7 月实际净退款金额。", first_pre, first, first_delta, None)
    facts.append(AgentTaskTurnFact("B1_CANONICAL", "T1", first_delta.category, first_transition.safe_projection(), tuple(item.safe_projection() for item in first.evidence), tuple(item.safe_projection() for item in first_contexts), _lifecycle("started", first.identity, version_before=None, version_after=1), 1, 1))

    second_delta = understand_turn("改成 8 月，并和 7 月比较。", action="continue", previous=first)
    second, second_transition = apply_delta(first, second_delta, owner_ref=owner)
    second_pre = second
    second = attach_evidence(second, ({"evidence_kind": "sql", "evidence_id": "m43-t2", "result_fingerprint": "oracle-july-august-delta"},))
    second_transition = replace(second_transition, after_identity=second.identity, changed_fields=tuple(dict.fromkeys((*second_transition.changed_fields, "evidence"))))
    second_contexts = _contexts("改成 8 月，并和 7 月比较。", second_pre, second, second_delta, first.identity)
    facts.append(AgentTaskTurnFact("B1_CANONICAL", "T2", second_delta.category, second_transition.safe_projection(), tuple(item.safe_projection() for item in second.evidence), tuple(item.safe_projection() for item in second_contexts), _lifecycle("active", second.identity, version_before=1, version_after=3), 1, 1))

    correction = understand_turn("更正为 2026 年 8 月实际净退款金额。", action="continue", previous=first)
    corrected, correction_transition = apply_delta(first, correction, owner_ref=owner)
    corrected_pre = corrected
    corrected = attach_evidence(corrected, ({"evidence_kind": "sql", "evidence_id": "m43-c1", "result_fingerprint": "oracle-august-180000"},))
    correction_transition = replace(correction_transition, after_identity=corrected.identity, changed_fields=tuple(dict.fromkeys((*correction_transition.changed_fields, "evidence"))))
    correction_contexts = _contexts("更正为 2026 年 8 月实际净退款金额。", corrected_pre, corrected, correction, first.identity)
    facts.append(AgentTaskTurnFact("B1_CORRECTION", "C1", correction.category, correction_transition.safe_projection(), tuple(item.safe_projection() for item in corrected.evidence), tuple(item.safe_projection() for item in correction_contexts), _lifecycle("active", corrected.identity, version_before=1, version_after=3), 1, 1))

    switch = understand_turn("换个问题，查询 2026 年 8 月实际净退款金额。", action="switch", previous=second)
    switched, switch_transition = apply_delta(second, switch, owner_ref=owner)
    switched_pre = switched
    switched = attach_evidence(switched, ({"evidence_kind": "sql", "evidence_id": "m43-s1", "result_fingerprint": "oracle-august-180000"},))
    switch_transition = replace(switch_transition, after_identity=switched.identity, changed_fields=tuple(dict.fromkeys((*switch_transition.changed_fields, "evidence"))))
    switch_contexts = _contexts("换个问题，查询 2026 年 8 月实际净退款金额。", switched_pre, switched, switch, second.identity)
    facts.append(AgentTaskTurnFact("B1_SWITCH_CANCEL", "S1", switch.category, switch_transition.safe_projection(), tuple(item.safe_projection() for item in switched.evidence), tuple(item.safe_projection() for item in switch_contexts), _lifecycle("switched", switched.identity, version_before=3, version_after=1), 1, 1))
    cancel = understand_turn("取消任务。", action="cancel", previous=switched)
    cancelled, cancel_transition = apply_delta(switched, cancel, owner_ref=owner)
    cancel_contexts = project_node_contexts(question="取消任务。", state=cancelled, delta=cancel, prior_state_identity=switched.identity)
    facts.append(AgentTaskTurnFact("B1_SWITCH_CANCEL", "S2", cancel.category, cancel_transition.safe_projection(), tuple(item.safe_projection() for item in cancelled.evidence), tuple(item.safe_projection() for item in cancel_contexts), _lifecycle("cancelled", cancelled.identity, version_before=1, version_after=3), 0, 1))

    ambiguous = understand_turn("改成另一个月。", action="continue", previous=first)
    pending, pending_transition = apply_delta(first, ambiguous, owner_ref=owner)
    pending_contexts = project_node_contexts(question="改成另一个月。", state=pending, delta=ambiguous, prior_state_identity=first.identity)
    facts.append(AgentTaskTurnFact("B1_CLARIFY", "N1", ambiguous.category, pending_transition.safe_projection(), tuple(item.safe_projection() for item in pending.evidence), tuple(item.safe_projection() for item in pending_contexts), _lifecycle("active", pending.identity, version_before=1, version_after=3), 0, 1))

    artifact = build_agent_scenario_v2(bundle=bundle, turns=tuple(facts))
    expected = bundle.payload["scenarios"][0]["turns"][1]["expected_value"]
    checks = {
        "contract_identity_bound": artifact["contract_identity"] == bundle.content_identity,
        "canonical_periods": dict(second.constraints)["periods"] == ("2026-07", "2026-08"),
        "old_sql_invalidated": second.evidence[0].validity == "invalidated",
        "new_sql_active": second.evidence[-1].validity == "active",
        "oracle": expected == {"july": 120000, "august": 180000, "delta": 60000, "rate": 0.5},
        "correction": correction.category == "correct_previous_understanding",
        "switch_cancel": switch.category == "switch_task" and cancelled.status == "cancelled",
        "clarification_zero_graph": pending.status == "clarification_required",
    }
    report = {"report_version": "m43-b1-deterministic-report-v1", "contract_identity": bundle.content_identity, "artifact_identity": artifact["content_identity"], "checks": checks, "passed": all(checks.values()), "external_calls": 0}
    return artifact, report


def main() -> None:
    artifact, report = _run()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "m43-agent-scenario-v2.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "m43-b1-deterministic-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# M43 B1 deterministic rehearsal", "", f"- passed: `{str(report['passed']).lower()}`", f"- external calls: `{report['external_calls']}`", f"- contract identity: `{report['contract_identity']}`", f"- artifact identity: `{report['artifact_identity']}`", "", "## Checks", ""]
    lines.extend(f"- [{'x' if passed else ' '}] {name}" for name, passed in report["checks"].items())
    (OUTPUT_DIR / "m43-b1-deterministic-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
