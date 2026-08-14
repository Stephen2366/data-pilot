"""M32 RAG retrieval Eval 的一次执行、分母、Gate 与 closed-world 合同。"""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from eval.rag_retrieval_contracts import (
    RAGRetrievalContractError,
    project_required_gate,
    project_retrieval_effect_summary,
    run_rag_retrieval_contract_suite,
    validate_completed_artifact,
)


def _rehash(artifact):
    encoded = json.dumps(
        artifact.unsigned_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return replace(artifact, artifact_identity=sha256(encoded).hexdigest())


def test_complete_suite_is_deterministic_and_required_gate_passes() -> None:
    first = run_rag_retrieval_contract_suite()
    second = run_rag_retrieval_contract_suite()
    assert first == second

    gate = project_required_gate(first)
    summary = project_retrieval_effect_summary(first)
    assert (gate.status, gate.failed, gate.not_observed) == ("passed", 0, 0)
    assert gate.passed == 20
    assert (summary.eligible, summary.observed, summary.passed, summary.failed, summary.not_observed) == (
        3,
        2,
        2,
        0,
        1,
    )


def test_each_scenario_has_one_execution_and_one_tool_call() -> None:
    artifact = run_rag_retrieval_contract_suite()
    assert len(artifact.execution_evidence) == len(artifact.selected_scenario_ids) == 6
    assert all(item.replicate == 1 for item in artifact.execution_evidence)
    assert all(item.adapter_calls == 1 for item in artifact.execution_evidence)


def test_external_unavailable_keeps_root_cause_observed_but_coverage_not_observed() -> None:
    artifact = run_rag_retrieval_contract_suite()
    unavailable = next(
        item for item in artifact.execution_evidence if item.scenario_id == "retriever_unavailable"
    )
    results = {
        item.assertion_id: item
        for item in artifact.assertion_results
        if item.scenario_id == "retriever_unavailable"
    }
    assert (unavailable.execution_outcome, unavailable.reason_code) == (
        "external_unavailable",
        "retrieval_unavailable",
    )
    assert results["execution_external_unavailable"].status == "passed"
    assert results["reason_correct"].status == "passed"
    assert results["gold_candidate_covered"].status == "not_observed"
    assert results["gold_candidate_covered"].effect == "advisory"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("not_completed", "artifact_not_completed"),
        ("runtime", "artifact_runtime_mismatch"),
        ("corpus", "artifact_corpus_missing"),
        ("scenario_missing", "artifact_scenario_mismatch"),
        ("scenario_duplicate", "artifact_scenario_mismatch"),
        ("execution_missing", "artifact_execution_mismatch"),
        ("execution_duplicate", "artifact_execution_mismatch"),
        ("assertion_missing", "artifact_assertion_mismatch"),
        ("assertion_duplicate", "artifact_assertion_mismatch"),
        ("effect", "artifact_assertion_mismatch"),
        ("hash", "artifact_hash_mismatch"),
    ],
)
def test_closed_world_validation_rejects_incomplete_extra_or_tampered_artifact(mutation: str, reason: str) -> None:
    artifact = run_rag_retrieval_contract_suite()
    if mutation == "not_completed":
        artifact = _rehash(replace(artifact, lifecycle_status="running"))
    elif mutation == "runtime":
        artifact = _rehash(replace(artifact, runtime_identity="other-runtime"))
    elif mutation == "corpus":
        artifact = _rehash(replace(artifact, corpus_identity=""))
    elif mutation == "scenario_missing":
        artifact = _rehash(replace(artifact, selected_scenario_ids=artifact.selected_scenario_ids[:-1]))
    elif mutation == "scenario_duplicate":
        artifact = _rehash(
            replace(artifact, selected_scenario_ids=(*artifact.selected_scenario_ids, artifact.selected_scenario_ids[-1]))
        )
    elif mutation == "execution_missing":
        artifact = _rehash(replace(artifact, execution_evidence=artifact.execution_evidence[:-1]))
    elif mutation == "execution_duplicate":
        artifact = _rehash(
            replace(artifact, execution_evidence=(*artifact.execution_evidence, artifact.execution_evidence[-1]))
        )
    elif mutation == "assertion_missing":
        artifact = _rehash(replace(artifact, assertion_results=artifact.assertion_results[:-1]))
    elif mutation == "assertion_duplicate":
        artifact = _rehash(
            replace(artifact, assertion_results=(*artifact.assertion_results, artifact.assertion_results[-1]))
        )
    elif mutation == "effect":
        changed = replace(artifact.assertion_results[0], effect="advisory")
        artifact = _rehash(replace(artifact, assertion_results=(changed, *artifact.assertion_results[1:])))
    else:
        artifact = replace(artifact, artifact_identity="tampered")

    with pytest.raises(RAGRetrievalContractError) as captured:
        validate_completed_artifact(artifact)
    assert captured.value.reason_code == reason


def test_failed_required_assertion_cannot_be_hidden_by_advisory_passes() -> None:
    artifact = run_rag_retrieval_contract_suite()
    index = next(index for index, item in enumerate(artifact.assertion_results) if item.effect == "required")
    changed = replace(artifact.assertion_results[index], status="failed")
    results = list(artifact.assertion_results)
    results[index] = changed
    artifact = _rehash(replace(artifact, assertion_results=tuple(results)))
    gate = project_required_gate(artifact)
    assert (gate.status, gate.failed) == ("failed", 1)
