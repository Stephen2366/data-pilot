"""M48-E/F：v6、阶段 assurance、fallback 与 private tamper 门。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from engine.phase4b.b6_contracts import load_b6_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v6_contracts import validate_agent_scenario_v6
from eval.phase4b_assurance import validate_phase4b_assurance
from scripts.rehearse_m48_b6 import build_from_probe


def _probe() -> dict[str, object]:
    return {
        "probe_id": "M48-P2", "decision": "continue", "seed_identity": "seed",
        "compact_identity": "compact", "canonical_versions": [1, 3, 5, 7, 9, 11],
        "compact_source_turn_range": [1, 5], "restart_continuation": "passed",
        "oracle": {"july": 120000, "august": 180000, "delta": 60000, "growth": "50%"},
        "processes": 2, "sql_guard_oracle": "passed",
        "business_subgraph": {
            "termination": "answer_ready",
            "consumption": {"selected": 3, "model_calls": 0, "total_tokens": 0},
        },
        "negative_paths": {
            "role_drift": {"reason_code": "task_unavailable", "invocations": 0},
            "stale_version": {"reason_code": "task_version_conflict", "invocations": 0},
            "competition": [
                {"action": "continue", "invocations": 1},
                {"action": "rejected", "invocations": 0},
            ],
        },
        "response_trace_redaction": "passed", "rows_after_cleanup": {"checkpoints": 0, "events": 0},
    }


def test_v6_and_assurance_are_closed_world_and_keep_claim_boundaries() -> None:
    bundle = load_b6_contract_bundle()
    scenario, assurance = build_from_probe(_probe())
    validate_agent_scenario_v6(scenario, bundle=bundle)
    validate_phase4b_assurance(assurance, bundle=bundle, scenario=scenario)
    assert [item["milestone"] for item in assurance["capability_matrix"]] == [f"B{i}" for i in range(7)]
    assert assurance["claim_boundary"]["subgraph"] == "server_controlled_experimental"
    assert assurance["claim_boundary"]["reserve"] == "sealed_not_run"


def test_v6_rejects_private_payload_even_after_resigning() -> None:
    bundle = load_b6_contract_bundle()
    scenario, _ = build_from_probe(_probe())
    poisoned = deepcopy(scenario)
    poisoned["cases"][0]["observations"]["raw_question"] = "private"
    case = poisoned["cases"][0]
    case["source_identity"] = canonical_hash({
        key: value for key, value in case.items() if key not in {"assertions", "source_identity"}
    })
    unsigned = {key: value for key, value in poisoned.items() if key != "artifact_identity"}
    poisoned["artifact_identity"] = canonical_hash(unsigned)
    with pytest.raises(ValueError, match="agent_scenario_v6_private_payload"):
        validate_agent_scenario_v6(poisoned, bundle=bundle)


def test_assurance_rejects_quality_claim_even_after_resigning() -> None:
    bundle = load_b6_contract_bundle()
    scenario, assurance = build_from_probe(_probe())
    poisoned = deepcopy(assurance)
    poisoned["claim_boundary"]["rag_quality_claim"] = "improved"
    unsigned = {key: value for key, value in poisoned.items() if key != "artifact_identity"}
    poisoned["artifact_identity"] = canonical_hash(unsigned)
    with pytest.raises(ValueError, match="phase4b_assurance_claim_boundary_invalid"):
        validate_phase4b_assurance(poisoned, bundle=bundle, scenario=scenario)
