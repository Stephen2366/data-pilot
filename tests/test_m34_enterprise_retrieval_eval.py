"""M34 retrieval scorer 的 multiset 与 closed-world artifact 测试。"""

from __future__ import annotations

import pytest

from engine.rag.enterprise_dataset import EnterpriseDatasetError, canonical_identity
from engine.rag.enterprise_retrieval_eval import (
    RETRIEVAL_EVAL_FORMAT,
    _coverage,
    validate_enterprise_retrieval_artifact,
)


def _artifact() -> dict[str, object]:
    execution = {
        "question_id": "q1",
        "adapter_calls": 1,
        "latency_ms": 12.5,
        "actual_matches": [],
    }
    identity_payload = {
        "format": RETRIEVAL_EVAL_FORMAT,
        "dataset_identity": "dataset",
        "question_set_identity": "questions",
        "split_identity": "split",
        "split_name": "diagnostic_dev",
        "profile_identity": "profile",
        "adapter_identity": "adapter",
        "retrieval_recipe_identity": "recipe",
        "executions": [{key: value for key, value in execution.items() if key != "latency_ms"}],
    }
    return {
        **{key: value for key, value in identity_payload.items() if key != "executions"},
        "status": "completed",
        "question_count": 1,
        "tool_call_count": 1,
        "artifact_identity": canonical_identity(identity_payload),
        "executions": [execution],
    }


def test_coverage_preserves_duplicate_logical_gold_cardinality() -> None:
    assert _coverage(("same", "same"), ("same",), 20)["coverage"] == 0.5
    assert _coverage(("same", "same"), ("same", "same"), 20)["all_gold"] is True


def test_artifact_validator_rejects_missing_question_and_hash_tamper() -> None:
    artifact = _artifact()
    validate_enterprise_retrieval_artifact(artifact, ("q1",))

    with pytest.raises(EnterpriseDatasetError) as missing:
        validate_enterprise_retrieval_artifact(artifact, ("q1", "q2"))
    assert missing.value.reason_code == "retrieval_eval_closed_world_mismatch"

    artifact["profile_identity"] = "changed"
    with pytest.raises(EnterpriseDatasetError) as tampered:
        validate_enterprise_retrieval_artifact(artifact, ("q1",))
    assert tampered.value.reason_code == "retrieval_eval_artifact_hash_mismatch"
