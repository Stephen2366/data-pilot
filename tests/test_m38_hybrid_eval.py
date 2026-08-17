"""M38 Hybrid Eval artifact 的闭集/篡改门禁。"""

from dataclasses import replace

import pytest

from eval.harness_hybrid_contracts import run_hybrid_contracts, validate_completed_hybrid_artifact


def test_hybrid_contract_family_is_closed_and_all_required_pass() -> None:
    """所有 M38 canonical 状态都在一次 execution/多断言协议下通过。"""

    artifact = run_hybrid_contracts()

    assert artifact.contract_version == "phase4-harness-hybrid-v1"
    assert len(artifact.execution_evidence) == 5
    assert len(artifact.assertions) == 25


def test_hybrid_artifact_rejects_missing_or_tampered_evidence() -> None:
    """缺 assertion 或把一题伪造为两次执行，均不能冒充 completed artifact。"""

    artifact = run_hybrid_contracts()
    with pytest.raises(ValueError):
        validate_completed_hybrid_artifact(replace(artifact, assertions=artifact.assertions[:-1]))
    tampered = list(artifact.execution_evidence)
    tampered[0] = replace(tampered[0], invocation_count=2)
    with pytest.raises(ValueError):
        validate_completed_hybrid_artifact(replace(artifact, execution_evidence=tuple(tampered)))
