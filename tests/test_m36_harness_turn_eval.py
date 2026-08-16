"""M36 sequence Eval artifact 的完整性与防伪测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eval.harness_turn_contracts import run_harness_turn_contracts, validate_completed_turn_artifact


def test_turn_eval_closes_all_sequences_with_bounded_graph_and_tool_counts() -> None:
    """owner/version/TTL/clear/concurrency/context/budget 共用统一 sequence 证据合同。"""

    artifact = run_harness_turn_contracts()

    assert artifact.contract_version == "phase4-harness-turn-v1"
    assert len(artifact.selected_sequence_ids) == 8
    assert all(item.status == "passed" for item in artifact.assertions)
    assert all(item.graph_invocation_count in {0, 1} for item in artifact.execution_evidence)


def test_turn_eval_rejects_missing_turn() -> None:
    """删除一个中间 turn 后不能留下看似完成的 artifact。"""

    artifact = run_harness_turn_contracts()
    victim = next(item for item in artifact.execution_evidence if item.turn_index == 2)
    broken = replace(
        artifact,
        execution_evidence=tuple(item for item in artifact.execution_evidence if item is not victim),
    )

    with pytest.raises(ValueError, match="缺 turn|顺序不闭合"):
        validate_completed_turn_artifact(broken)


def test_turn_eval_rejects_duplicate_execution_and_missing_assertion() -> None:
    """重复 execution 或少一条 typed assertion 都必须 fail closed。"""

    artifact = run_harness_turn_contracts()
    duplicate = replace(artifact, execution_evidence=(*artifact.execution_evidence, artifact.execution_evidence[0]))
    missing_assertion = replace(artifact, assertions=artifact.assertions[:-1])

    with pytest.raises(ValueError, match="execution 重复"):
        validate_completed_turn_artifact(duplicate)
    with pytest.raises(ValueError, match="assertion"):
        validate_completed_turn_artifact(missing_assertion)
