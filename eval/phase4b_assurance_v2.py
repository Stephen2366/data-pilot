"""M49-C：合同身份与执行证据身份分权的 Phase 4B assurance v2。"""

from __future__ import annotations

from typing import Any, Mapping

from engine.phase4b.b6_contracts import B6ContractBundle
from engine.phase4b.identity import canonical_hash
from eval.agent_scenario_v7_contracts import validate_agent_scenario_v7

ARTIFACT_VERSION = "phase4b-assurance-artifact-v2"
MILESTONES = tuple(f"B{index}" for index in range(7))
MATRIX_FIELDS = {
    "milestone", "module", "status", "contract_identity", "evidence_locator", "evidence_identity",
}


def _assurance_status(matrix: list[Mapping[str, Any]], scenario_status: str) -> str:
    """用最差 required 状态收敛总票，避免部分 available 掩盖 failed/unverified。"""

    if scenario_status == "failed" or any(item["status"] == "blocked" for item in matrix):
        return "failed"
    if scenario_status != "completed" or any(item["status"] == "unverified" for item in matrix):
        return "inconclusive"
    return "completed"


def build_phase4b_assurance_v2(
    *, bundle: B6ContractBundle, scenario: Mapping[str, Any],
    contract_identities: Mapping[str, str], milestone_evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """只有独立 execution evidence 可把 milestone 标成 available。"""

    validate_agent_scenario_v7(scenario, bundle=bundle)
    if tuple(contract_identities) != MILESTONES or tuple(milestone_evidence) != MILESTONES:
        raise ValueError("phase4b_assurance_v2_milestone_order_invalid")
    matrix: list[dict[str, Any]] = []
    for index, milestone in enumerate(MILESTONES):
        evidence = milestone_evidence[milestone]
        observed = evidence.get("status", "not_observed")
        status = {"passed": "available", "failed": "blocked", "not_observed": "unverified"}.get(observed)
        if status is None:
            raise ValueError("phase4b_assurance_v2_evidence_status_invalid")
        matrix.append({
            "milestone": milestone,
            "module": f"M{42 + index}",
            "status": status,
            "contract_identity": contract_identities[milestone],
            "evidence_locator": evidence.get("evidence_locator"),
            "evidence_identity": evidence.get("evidence_identity"),
        })
    unsigned = {
        "artifact_version": ARTIFACT_VERSION,
        "status": _assurance_status(matrix, str(scenario["status"])),
        "scenario_artifact_identity": scenario["artifact_identity"],
        "capability_matrix": matrix,
        "compatibility": dict(bundle.payload["compatibility"]),
        "claim_boundary": {
            "technical_integration": "evidence_gated",
            "pipeline_default": True,
            "subgraph": "server_controlled_experimental",
            "rag_quality_claim": "not_claimed",
            "production_certification": "not_claimed",
            "reserve": "sealed_not_run",
        },
    }
    artifact = {**unsigned, "artifact_identity": canonical_hash(unsigned)}
    validate_phase4b_assurance_v2(artifact, bundle=bundle, scenario=scenario)
    return artifact


def validate_phase4b_assurance_v2(
    payload: Mapping[str, Any], *, bundle: B6ContractBundle, scenario: Mapping[str, Any],
) -> None:
    """拒绝 contract 自证、缺证据 available、状态伪造和越界 claim。"""

    expected = {
        "artifact_version", "status", "scenario_artifact_identity", "capability_matrix",
        "compatibility", "claim_boundary", "artifact_identity",
    }
    if set(payload) != expected or payload.get("artifact_version") != ARTIFACT_VERSION:
        raise ValueError("phase4b_assurance_v2_shape_invalid")
    unsigned = {key: value for key, value in payload.items() if key != "artifact_identity"}
    if payload["artifact_identity"] != canonical_hash(unsigned):
        raise ValueError("phase4b_assurance_v2_identity_mismatch")
    if payload["scenario_artifact_identity"] != scenario["artifact_identity"]:
        raise ValueError("phase4b_assurance_v2_scenario_mismatch")
    matrix = payload["capability_matrix"]
    if [item.get("milestone") for item in matrix] != list(MILESTONES):
        raise ValueError("phase4b_assurance_v2_matrix_order_invalid")
    for item in matrix:
        if set(item) != MATRIX_FIELDS or item["status"] not in {"available", "blocked", "unverified"}:
            raise ValueError("phase4b_assurance_v2_matrix_invalid")
        if item["status"] == "available":
            if not item["evidence_locator"] or not item["evidence_identity"]:
                raise ValueError("phase4b_assurance_v2_available_without_evidence")
            if item["evidence_identity"] == item["contract_identity"]:
                raise ValueError("phase4b_assurance_v2_contract_self_attestation")
        elif item["status"] == "unverified" and (item["evidence_locator"] is not None or item["evidence_identity"] is not None):
            raise ValueError("phase4b_assurance_v2_unverified_has_evidence")
    if payload["status"] != _assurance_status(matrix, str(scenario["status"])):
        raise ValueError("phase4b_assurance_v2_status_mismatch")
    if payload["compatibility"] != bundle.payload["compatibility"]:
        raise ValueError("phase4b_assurance_v2_compatibility_invalid")
    if payload["claim_boundary"] != {
        "technical_integration": "evidence_gated", "pipeline_default": True,
        "subgraph": "server_controlled_experimental", "rag_quality_claim": "not_claimed",
        "production_certification": "not_claimed", "reserve": "sealed_not_run",
    }:
        raise ValueError("phase4b_assurance_v2_claim_boundary_invalid")
