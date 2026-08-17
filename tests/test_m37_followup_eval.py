"""M37 follow-up sequence artifact 的正常完成与篡改拒绝。"""

from dataclasses import replace

import pytest

from eval.harness_followup_contracts import (
    ASSERTION_IDS,
    FOLLOW_UP_CONTRACT_VERSION,
    SCENARIOS,
    run_harness_followup_contracts,
    validate_completed_followup_artifact,
)


def test_followup_contract_family_is_closed_and_all_required_pass() -> None:
    """完整 family 必须覆盖 10 条序列并通过全部 50 条 required assertion。"""

    artifact = run_harness_followup_contracts()

    assert artifact.contract_version == FOLLOW_UP_CONTRACT_VERSION
    assert artifact.selected_sequence_ids == tuple(item.scenario_id for item in SCENARIOS)
    assert len(artifact.assertions) == len(SCENARIOS) * len(ASSERTION_IDS)
    assert {item.status for item in artifact.assertions} == {"passed"}
    assert len(artifact.artifact_identity) == 64


def test_completed_validator_rejects_missing_assertion_duplicate_and_old_id_reuse() -> None:
    """completed validator 必须拒绝残缺、重复和旧 run Evidence 注入。"""

    artifact = run_harness_followup_contracts()
    with pytest.raises(ValueError, match="assertion"):
        validate_completed_followup_artifact(replace(artifact, assertions=artifact.assertions[:-1]))
    with pytest.raises(ValueError, match="重复"):
        validate_completed_followup_artifact(
            replace(artifact, execution_evidence=(*artifact.execution_evidence, artifact.execution_evidence[0]))
        )
    accepted_index = next(
        index for index, item in enumerate(artifact.execution_evidence) if item.turn_action == "follow_up"
    )
    tampered = list(artifact.execution_evidence)
    tampered[accepted_index] = replace(tampered[accepted_index], old_evidence_id_reused=True)
    with pytest.raises(ValueError, match="旧 run Evidence"):
        validate_completed_followup_artifact(replace(artifact, execution_evidence=tuple(tampered)))
