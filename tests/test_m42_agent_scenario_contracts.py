"""M42-D Agent Scenario skeleton 的 completed 与篡改拒绝合同。"""

from __future__ import annotations

from copy import deepcopy

import pytest

from engine.phase4b.contracts import load_b0_contract_bundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_contracts import (
    AgentScenarioContractError,
    build_b0_fixture_evidence,
    build_completed_artifact,
    validate_completed_artifact,
)


def _artifact() -> tuple[dict, object]:
    """用冻结 B0 catalog 构造一份可被逐项篡改的 completed skeleton。"""

    bundle = load_b0_contract_bundle()
    artifact = build_completed_artifact(
        bundle=bundle,
        run_id="m42-agent-skeleton",
        executions=build_b0_fixture_evidence(bundle),
        runtime_identity={
            "runtime_family": "phase4b-agent-runtime-v1",
            "seed_profile": "phase4b",
            "caller_fixture": "phase4b-minimal-caller-v1",
            "provider": "none",
        },
    )
    return artifact, bundle


def _resign(artifact: dict) -> None:
    """只重签顶层 identity，让测试能够继续命中更深层的 closed-world Gate。"""

    artifact["artifact_identity"] = canonical_hash({key: value for key, value in artifact.items() if key != "artifact_identity"})


def test_completed_skeleton_is_safe_and_closed_world() -> None:
    artifact, bundle = _artifact()
    validate_completed_artifact(artifact, bundle=bundle)
    assert len(artifact["executions"]) == 7
    assert "answer" not in str(artifact).lower()
    assert "sql rows" not in str(artifact).lower()
    assert {row["owner"] for row in artifact["capability_matrix"] if row["status"] == "unavailable"} == {
        "M43", "M44", "M45", "M46", "M47", "M48"
    }


@pytest.mark.parametrize("mutation", ["missing_execution", "extra_execution", "duplicate_turn", "duplicate_assertion", "identity_drift", "hash_tamper"])
def test_completed_skeleton_rejects_every_closed_world_tamper(mutation: str) -> None:
    artifact, bundle = _artifact()
    if mutation == "missing_execution":
        artifact["executions"].pop()
        _resign(artifact)
    elif mutation == "extra_execution":
        artifact["executions"].append(deepcopy(artifact["executions"][0]))
        _resign(artifact)
    elif mutation == "duplicate_turn":
        artifact["executions"][0]["turns"].append(deepcopy(artifact["executions"][0]["turns"][0]))
        unsigned = {key: value for key, value in artifact["executions"][0].items() if key != "execution_identity"}
        artifact["executions"][0]["execution_identity"] = canonical_hash(unsigned)
        _resign(artifact)
    elif mutation == "duplicate_assertion":
        turn = artifact["executions"][0]["turns"][0]
        turn["assertion_results"].append(deepcopy(turn["assertion_results"][0]))
        unsigned = {key: value for key, value in artifact["executions"][0].items() if key != "execution_identity"}
        artifact["executions"][0]["execution_identity"] = canonical_hash(unsigned)
        _resign(artifact)
    elif mutation == "identity_drift":
        artifact["run_spec"]["contract_identity"] = "drift"
        artifact["run_spec_identity"] = canonical_hash(artifact["run_spec"])
        _resign(artifact)
    else:
        artifact["artifact_identity"] = "tampered"
    with pytest.raises(AgentScenarioContractError):
        validate_completed_artifact(artifact, bundle=bundle)
