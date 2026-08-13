"""M31 `phase4-v1` 一题一次与 closed-world artifact 门。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from engine.rag.catalog import build_staged_catalog
from eval.phase4_contracts import (
    Phase4ContractError,
    project_required_gate,
    run_phase4_contract_suite,
    validate_completed_artifact,
)


def _artifact(tmp_path: Path):
    return run_phase4_contract_suite(staged=build_staged_catalog(), root=tmp_path / "phase4-runtime")


def test_phase4_contract_suite_uses_one_execution_per_scenario_and_passes_gate(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    gate = project_required_gate(artifact)
    assert gate.status == "passed"
    assert gate.passed == len(artifact.assertion_results)
    assert gate.failed == gate.not_observed == 0
    assert len(artifact.execution_evidence) == len(artifact.selected_scenario_ids)
    for result in artifact.assertion_results:
        assert result.evidence_ref == f"execution:{result.scenario_id}:1"


def test_phase4_contract_suite_can_repeat_in_same_runtime_root(tmp_path: Path) -> None:
    root = tmp_path / "repeatable-runtime"
    first = run_phase4_contract_suite(staged=build_staged_catalog(), root=root)
    second = run_phase4_contract_suite(staged=build_staged_catalog(), root=root)
    assert first == second
    assert project_required_gate(second).status == "passed"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("missing_scenario", "artifact_scenario_mismatch"),
        ("extra_scenario", "artifact_scenario_mismatch"),
        ("duplicate_execution", "artifact_execution_mismatch"),
        ("missing_assertion", "artifact_assertion_mismatch"),
        ("duplicate_assertion", "artifact_assertion_mismatch"),
        ("policy_mismatch", "artifact_policy_mismatch"),
        ("caller_mismatch", "artifact_caller_mismatch"),
        ("runtime_mismatch", "artifact_runtime_mismatch"),
        ("corpus_missing", "artifact_corpus_mismatch"),
        ("release_missing", "artifact_release_mismatch"),
        ("contract_mismatch", "artifact_contract_mismatch"),
        ("hash_mismatch", "artifact_hash_mismatch"),
    ],
)
def test_completed_artifact_closed_world_rejects_tampering(tmp_path: Path, mutation: str, reason: str) -> None:
    artifact = _artifact(tmp_path)
    if mutation == "missing_scenario":
        artifact = replace(artifact, selected_scenario_ids=artifact.selected_scenario_ids[:-1])
    elif mutation == "extra_scenario":
        artifact = replace(artifact, selected_scenario_ids=(*artifact.selected_scenario_ids, "extra"))
    elif mutation == "duplicate_execution":
        artifact = replace(artifact, execution_evidence=(*artifact.execution_evidence, artifact.execution_evidence[-1]))
    elif mutation == "missing_assertion":
        artifact = replace(artifact, assertion_results=artifact.assertion_results[:-1])
    elif mutation == "duplicate_assertion":
        artifact = replace(artifact, assertion_results=(*artifact.assertion_results, artifact.assertion_results[-1]))
    elif mutation == "policy_mismatch":
        artifact = replace(artifact, outbound_policy_identity="other-policy")
    elif mutation == "caller_mismatch":
        artifact = replace(artifact, caller_fixture_identity="other-callers")
    elif mutation == "runtime_mismatch":
        artifact = replace(artifact, runtime_identity="other-runtime")
    elif mutation == "corpus_missing":
        artifact = replace(artifact, corpus_identity="")
    elif mutation == "release_missing":
        artifact = replace(artifact, release_identity="")
    elif mutation == "contract_mismatch":
        artifact = replace(artifact, contract_identity="other-contract")
    else:
        artifact = replace(artifact, artifact_identity="tampered")
    with pytest.raises(Phase4ContractError) as captured:
        validate_completed_artifact(artifact)
    assert captured.value.reason_code == reason


def test_failed_required_assertion_cannot_be_hidden_by_other_passes(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    failed = replace(artifact.assertion_results[0], status="failed")
    artifact = replace(artifact, assertion_results=(failed, *artifact.assertion_results[1:]))
    encoded = json.dumps(
        artifact.unsigned_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    artifact = replace(artifact, artifact_identity=hashlib.sha256(encoded).hexdigest())
    gate = project_required_gate(artifact)
    assert gate.status == "failed"
    assert gate.failed == 1
