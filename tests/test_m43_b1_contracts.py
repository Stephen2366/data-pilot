"""M43-A/F B1 manifest 与 Agent Scenario v2 回归。"""

import copy

import pytest

from engine.phase4b.b1_contracts import load_b1_contract_bundle
from eval.agent_scenario_v2_contracts import AgentTaskTurnFact, build_agent_scenario_v2, validate_agent_scenario_v2


def test_b1_contract_is_additive_and_canonical_oracle_is_frozen() -> None:
    bundle = load_b1_contract_bundle()
    assert bundle.payload["predecessor_contract_identity"] == "6543883bb7c82bbaf2052d20631f26c023fb757d0c73e667e6899fd8883c56f2"
    turns = bundle.payload["scenarios"][0]["turns"]
    assert turns[1]["expected_value"] == {"july": 120000, "august": 180000, "delta": 60000, "rate": 0.5}


def test_agent_scenario_v2_is_closed_world_and_identity_bound() -> None:
    bundle = load_b1_contract_bundle()
    fact = AgentTaskTurnFact(
        "B1_CANONICAL", "T1", "start_task",
        {"category": "start_task", "before_identity": None, "after_identity": "safe", "changed_fields": [], "invalidated_evidence_count": 0},
        (), (),
        {"task_safe_ref": "task:safe", "action": "started", "reason_code": "task_started", "version_before": None, "version_after": 1, "state_identity": "safe", "previous_task_safe_ref": None},
        1, 1,
    )
    artifact = build_agent_scenario_v2(bundle=bundle, turns=(fact,))
    validate_agent_scenario_v2(artifact)
    tampered = copy.deepcopy(artifact)
    tampered["turns"][0]["answer"] = "private"
    with pytest.raises(ValueError, match="identity_mismatch|turn_invalid"):
        validate_agent_scenario_v2(tampered)
