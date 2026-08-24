"""M44-F：v3 artifact 从 action ledger 同源构造并拒绝篡改。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from engine.phase4b.b2_contracts import load_b2_contract_bundle
from engine.phase4b.identity import canonical_hash
from engine.phase4b.loop_contracts import (
    ActionAttempt, BudgetLedger, BudgetProfile, EvidenceDelta, ProgressDecision, ResourceConsumption,
)
from eval.agent_scenario_v3_contracts import build_agent_scenario_v3, validate_agent_scenario_v3


def _turn() -> dict[str, object]:
    bundle = load_b2_contract_bundle()
    before = BudgetLedger(BudgetProfile(**bundle.payload["budget_profile"]))
    consumed = ResourceConsumption(actions=1, deep_tools=1, sql_actions=1, token_usage_observed=False)
    after = before.consume(consumed)
    ref = {"evidence_id": "sql-e1", "evidence_kind": "sql"}
    action = ActionAttempt(
        ordinal=1,
        action_id="collect_sql_evidence",
        requirement_identity="sql:metric:2026-08",
        input_fingerprint="input-fp",
        duplicate_key="duplicate-fp",
        status="completed",
        observation={
            "tool_name": "text2sql", "route": "sql", "execution_status": "completed",
            "answer_status": "complete", "safety_status": "passed", "reason_code": "sql_completed",
            "error_type": None, "evidence_refs": [ref], "diagnostics": {},
        },
        budget_before=before.safe_projection(),
        consumed=consumed,
        budget_after=after.safe_projection(),
        evidence_delta=EvidenceDelta(added=(ref,)),
        progress=ProgressDecision(True, False, "coverage_increased"),
    )
    return {
        "scenario_id": "T3", "turn_id": "T3",
        "task_delta": {"category": "start_task"},
        "task_state": {"state_version": "phase4b-task-state-v2"},
        "actions": [action.safe_projection()], "budget": after.safe_projection(),
        "node_contexts": [],
        "termination": {
            "reason": "answer_ready", "detail_code": "answer_ready",
            "active_requirement_identities": ["sql:metric:2026-08"],
            "unresolved_requirement_identities": [],
        },
        "runtime_identity": {"format": "phase4b-agent-loop-langgraph-v1"},
        "assertions": [["required:value", "passed"], ["advisory:latency", "not_observed"]],
    }


def _artifact() -> dict[str, object]:
    bundle = load_b2_contract_bundle()
    return build_agent_scenario_v3(
        bundle=bundle,
        run_spec={
            "run_id": "m44-v3-test", "seed_identity": "seed-v1", "caller_identity": "caller-safe-v1",
            "knowledge_runtime_identities": ["business-release-v1"],
            "policy_identities": ["sql-guard-v1", "outbound-v1"],
        },
        turns=(_turn(),),
    )


def _resign(artifact: dict[str, object]) -> None:
    run_spec = artifact["run_spec"]
    artifact["run_spec_identity"] = canonical_hash(run_spec)
    artifact["artifact_identity"] = canonical_hash(
        {key: value for key, value in artifact.items() if key != "artifact_identity"}
    )


def test_v3_completed_artifact_is_closed_and_identity_bound() -> None:
    artifact = _artifact()
    validate_agent_scenario_v3(artifact, bundle=load_b2_contract_bundle())
    assert artifact["status"] == "completed"


@pytest.mark.parametrize("mutation", ["duplicate", "budget", "private", "assertion"])
def test_v3_rejects_action_budget_private_and_assertion_mutations(mutation: str) -> None:
    artifact = deepcopy(_artifact())
    turn = artifact["turns"][0]
    if mutation == "duplicate":
        duplicate = deepcopy(turn["actions"][0])
        duplicate["ordinal"] = 2
        turn["actions"].append(duplicate)
        turn["budget"] = duplicate["budget_after"]
    elif mutation == "budget":
        turn["actions"][0]["budget_after"]["consumed"]["actions"] = 2
        turn["budget"] = turn["actions"][0]["budget_after"]
    elif mutation == "private":
        turn["task_state"]["rows"] = [{"secret": 1}]
    else:
        turn["assertions"][0][1] = "skipped"
    _resign(artifact)
    with pytest.raises(ValueError):
        validate_agent_scenario_v3(artifact, bundle=load_b2_contract_bundle())
