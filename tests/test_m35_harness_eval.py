"""M35 独立 Harness Eval 的 artifact 完整性测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from eval.harness_contracts import run_harness_contracts, validate_completed_artifact


def test_harness_eval_runs_one_graph_per_scenario_and_closes_required_assertions() -> None:
    """route、状态与唯一 Tool 断言复用同一 execution，不重跑 Graph。"""

    artifact = run_harness_contracts()

    assert artifact.contract_version == "phase4-harness-v1"
    assert len(artifact.execution_evidence) == 5
    assert all(item.invocation_count == 1 for item in artifact.execution_evidence)
    assert all(item.status == "passed" for item in artifact.assertions)


def test_harness_eval_rejects_missing_execution_evidence() -> None:
    """closed-world validator 不允许删掉一题后仍生成看似可信的 artifact。"""

    artifact = run_harness_contracts()
    broken = replace(artifact, execution_evidence=artifact.execution_evidence[:-1])

    with pytest.raises(ValueError, match="每题必须"):
        validate_completed_artifact(broken)
