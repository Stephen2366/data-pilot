"""M48-E：B0～B6 technical capability/compatibility assurance。"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b6_contracts import B6ContractBundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v6_contracts import validate_agent_scenario_v6

ARTIFACT_VERSION = "phase4b-assurance-artifact-v1"
MILESTONES = tuple(f"B{index}" for index in range(7))


def build_phase4b_assurance(
    *, bundle: B6ContractBundle, scenario: Mapping[str, Any], contract_identities: Mapping[str, str],
) -> dict[str, Any]:
    """聚合 B0～B6；available 只表示技术门闭合，不外推生产或质量结论。"""

    validate_agent_scenario_v6(scenario, bundle=bundle)
    if tuple(contract_identities) != MILESTONES:
        raise ValueError("phase4b_assurance_contract_order_invalid")
    matrix = [
        {
            "milestone": milestone, "module": f"M{42 + index}", "status": "available",
            "contract_identity": contract_identities[milestone],
            "evidence_identity": scenario["artifact_identity"] if milestone == "B6" else contract_identities[milestone],
        }
        for index, milestone in enumerate(MILESTONES)
    ]
    unsigned = {
        "artifact_version": ARTIFACT_VERSION, "status": "completed",
        "scenario_artifact_identity": scenario["artifact_identity"],
        "capability_matrix": matrix,
        "compatibility": dict(bundle.payload["compatibility"]),
        "claim_boundary": {
            "technical_integration": "completed",
            "pipeline_default": True,
            "subgraph": "server_controlled_experimental",
            "rag_quality_claim": "not_claimed",
            "production_certification": "not_claimed",
            "reserve": "sealed_not_run",
        },
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_phase4b_assurance(artifact, bundle=bundle, scenario=scenario)
    return artifact


def validate_phase4b_assurance(
    payload: Mapping[str, Any], *, bundle: B6ContractBundle, scenario: Mapping[str, Any],
) -> None:
    """拒绝缺模块、越界 claim、旧 rollout 漂移或重算 hash 后的语义篡改。"""

    expected = {
        "artifact_version", "status", "scenario_artifact_identity", "capability_matrix",
        "compatibility", "claim_boundary", "artifact_identity",
    }
    if set(payload) != expected or payload["artifact_version"] != ARTIFACT_VERSION or payload["status"] != "completed":
        raise ValueError("phase4b_assurance_shape_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("phase4b_assurance_identity_mismatch")
    if payload["scenario_artifact_identity"] != scenario["artifact_identity"]:
        raise ValueError("phase4b_assurance_scenario_mismatch")
    matrix = payload["capability_matrix"]
    if [item.get("milestone") for item in matrix] != list(MILESTONES) or any(item.get("status") != "available" for item in matrix):
        raise ValueError("phase4b_assurance_matrix_invalid")
    if payload["compatibility"] != bundle.payload["compatibility"]:
        raise ValueError("phase4b_assurance_compatibility_invalid")
    if payload["claim_boundary"] != {
        "technical_integration": "completed", "pipeline_default": True,
        "subgraph": "server_controlled_experimental", "rag_quality_claim": "not_claimed",
        "production_certification": "not_claimed", "reserve": "sealed_not_run",
    }:
        raise ValueError("phase4b_assurance_claim_boundary_invalid")

