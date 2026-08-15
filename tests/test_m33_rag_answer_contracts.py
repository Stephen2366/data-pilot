"""M33 RAG Answer Eval 的一次执行、分母、Gate 与 closed-world 合同。"""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from eval.rag_answer_contracts import (
    RAGAnswerContractError,
    project_answer_effect_summary,
    project_required_gate,
    run_rag_answer_contract_suite,
    validate_completed_artifact,
)


def _rehash(artifact):
    """篡改 fixture 后重算 hash，使测试能定位更深层合同。"""

    encoded = json.dumps(
        artifact.unsigned_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return replace(artifact, artifact_identity=sha256(encoded).hexdigest())


def test_complete_suite_is_deterministic_and_required_gate_passes() -> None:
    """同一输入重复执行必须字节级稳定，required Gate 全绿。"""

    first = run_rag_answer_contract_suite()
    second = run_rag_answer_contract_suite()
    assert first == second

    gate = project_required_gate(first)
    summary = project_answer_effect_summary(first)
    assert (gate.status, gate.passed, gate.failed, gate.not_observed) == ("passed", 60, 0, 0)
    assert (summary.eligible, summary.observed, summary.passed, summary.failed, summary.not_observed) == (
        3, 2, 2, 0, 1
    )


def test_each_scenario_has_exactly_one_answer_flow_execution() -> None:
    """每个场景只能运行一次流程，scorer 不得暗中重跑。"""

    artifact = run_rag_answer_contract_suite()
    assert len(artifact.selected_scenario_ids) == len(artifact.execution_evidence) == 9
    assert all(item.replicate == 1 and item.knowledge_tool_calls == 1 for item in artifact.execution_evidence)


def test_technical_unavailable_keeps_state_observed_but_quality_not_observed() -> None:
    """技术故障的状态可评分，但答案质量必须留作未观察。"""

    artifact = run_rag_answer_contract_suite()
    execution = next(item for item in artifact.execution_evidence if item.scenario_id == "retriever_unavailable")
    results = {
        item.assertion_id: item
        for item in artifact.assertion_results
        if item.scenario_id == "retriever_unavailable"
    }
    assert (execution.execution_status, execution.reason_code) == ("external_unavailable", "retrieval_unavailable")
    assert results["axes_correct"].status == results["reason_correct"].status == "passed"
    assert results["answer_quality_observed"].effect == "advisory"
    assert results["answer_quality_observed"].status == "not_observed"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("not_completed", "artifact_not_completed"),
        ("runtime", "artifact_runtime_mismatch"),
        ("composer", "artifact_runtime_mismatch"),
        ("policy", "artifact_runtime_mismatch"),
        ("corpus", "artifact_corpus_missing"),
        ("scenario_missing", "artifact_scenario_mismatch"),
        ("scenario_duplicate", "artifact_scenario_mismatch"),
        ("execution_missing", "artifact_execution_mismatch"),
        ("replicate", "artifact_execution_mismatch"),
        ("assertion_missing", "artifact_assertion_mismatch"),
        ("assertion_duplicate", "artifact_assertion_mismatch"),
        ("effect", "artifact_assertion_mismatch"),
        ("evidence", "artifact_evidence_mismatch"),
        ("hash", "artifact_hash_mismatch"),
    ],
)
def test_closed_world_validation_rejects_incomplete_extra_or_tampered_artifact(mutation: str, reason: str) -> None:
    """缺失、重复或 identity 篡改均不能投影为可信 completed artifact。"""

    artifact = run_rag_answer_contract_suite()
    if mutation == "not_completed":
        artifact = _rehash(replace(artifact, lifecycle_status="running"))
    elif mutation == "runtime":
        artifact = _rehash(replace(artifact, answer_flow_identity="other-runtime"))
    elif mutation == "composer":
        artifact = _rehash(replace(artifact, composer_identity="other-composer"))
    elif mutation == "policy":
        artifact = _rehash(replace(artifact, authorization_policy_identity="other-policy"))
    elif mutation == "corpus":
        artifact = _rehash(replace(artifact, corpus_identity=""))
    elif mutation == "scenario_missing":
        artifact = _rehash(replace(artifact, selected_scenario_ids=artifact.selected_scenario_ids[:-1]))
    elif mutation == "scenario_duplicate":
        artifact = _rehash(replace(artifact, selected_scenario_ids=(*artifact.selected_scenario_ids, artifact.selected_scenario_ids[-1])))
    elif mutation == "execution_missing":
        artifact = _rehash(replace(artifact, execution_evidence=artifact.execution_evidence[:-1]))
    elif mutation == "replicate":
        changed = replace(artifact.execution_evidence[0], replicate=2)
        artifact = _rehash(replace(artifact, execution_evidence=(changed, *artifact.execution_evidence[1:])))
    elif mutation == "assertion_missing":
        artifact = _rehash(replace(artifact, assertion_results=artifact.assertion_results[:-1]))
    elif mutation == "assertion_duplicate":
        artifact = _rehash(replace(artifact, assertion_results=(*artifact.assertion_results, artifact.assertion_results[-1])))
    elif mutation == "effect":
        changed = replace(artifact.assertion_results[0], effect="advisory")
        artifact = _rehash(replace(artifact, assertion_results=(changed, *artifact.assertion_results[1:])))
    elif mutation == "evidence":
        changed = replace(artifact.assertion_results[0], evidence_ref="other-execution")
        artifact = _rehash(replace(artifact, assertion_results=(changed, *artifact.assertion_results[1:])))
    else:
        artifact = replace(artifact, artifact_identity="tampered")

    with pytest.raises(RAGAnswerContractError) as captured:
        validate_completed_artifact(artifact)
    assert captured.value.reason_code == reason


def test_failed_required_assertion_cannot_be_hidden_by_advisory_passes() -> None:
    """任何 required 失败都不能被 advisory 通过项稀释。"""

    artifact = run_rag_answer_contract_suite()
    index = next(index for index, item in enumerate(artifact.assertion_results) if item.effect == "required")
    results = list(artifact.assertion_results)
    results[index] = replace(results[index], status="failed")
    artifact = _rehash(replace(artifact, assertion_results=tuple(results)))

    gate = project_required_gate(artifact)
    assert (gate.status, gate.failed) == ("failed", 1)
