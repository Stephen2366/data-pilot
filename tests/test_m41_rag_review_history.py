"""M41 review 来源、严格 compare 与 M34 historical 只读边界。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.rag.enterprise_answer_eval import finalize_answer_artifact
from eval.rag_e2e_contracts import RAGEvalContractError, canonical_hash
from eval.rag_e2e_review import build_review_bundle, compare_completed, verify_review_sources
from eval.rag_m34_history import import_m34_answer_history
from tests.test_m41_rag_e2e_contracts import _run


def _resign(artifact: dict) -> dict:
    artifact["run_spec_identity"] = canonical_hash(artifact["run_spec"])
    unsigned = {key: value for key, value in artifact.items() if key != "artifact_identity"}
    artifact["artifact_identity"] = canonical_hash(unsigned)
    return artifact


def test_review_bundle_verifies_hashes_and_detects_checkpoint_tamper(tmp_path: Path) -> None:
    _run(tmp_path)
    artifact_path = tmp_path / "artifact.json"
    bundle = build_review_bundle(
        artifact_path=artifact_path,
        checkpoint_root=tmp_path / "checkpoints",
        reviewer="test-reviewer",
    )
    assert verify_review_sources(bundle) == {"artifact": 1, "checkpoints": 2}

    checkpoint = Path(bundle["records"][0]["source_checkpoint"]["path"])
    checkpoint.write_text(checkpoint.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(RAGEvalContractError, match="hash"):
        verify_review_sources(bundle)


def test_compare_accepts_only_identical_protocol_and_runtime(tmp_path: Path) -> None:
    left = _run(tmp_path)
    right = deepcopy(left)
    right["run_spec"]["run_id"] = "m41-test-smoke-right"
    _resign(right)
    assert compare_completed(left, right)["strictly_comparable"] is True

    right["run_spec"]["runtime"]["model"] = "different-model"
    _resign(right)
    with pytest.raises(RAGEvalContractError, match="not_comparable|identity"):
        compare_completed(left, right)


def test_m34_importer_is_offline_and_marks_missing_product_layers(tmp_path: Path) -> None:
    execution = {
        "question_id": "q1", "question_type": "basic", "source_types": ["jira"],
        "document_cardinality": "single_document", "expected_document_ids": ["d1"],
        "gold_answer": "gold", "answer_facts": ["gold"], "outcome": "contract_rejected",
        "internal_reason_code": "composer_output_invalid", "result": None,
        "cited_logical_document_ids": [],
        "document_coverage": {"covered": 0, "expected": 1, "coverage": 0.0, "all_gold": False},
        "fact_checks": [{"fact": "gold", "exactly_supported": False}], "exact_fact_coverage": 0.0,
        "provider_usage_delta": {"request_count": 1, "total_tokens": 10},
        "composer_attempt": {"status": "succeeded"}, "answer_flow_calls": 1,
    }
    artifact = finalize_answer_artifact(
        dataset_identity="dataset", question_set_identity="questions", split_identity="split",
        profile_identity="profile", composer_identity="composer", question_ids=("q1",),
        executions=(execution,),
    )
    path = tmp_path / "m34.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")
    view = import_m34_answer_history(path)
    assert view["is_product_harness_e2e"] is False
    assert {"api", "router", "harness"} <= set(view["not_observed_layers"])
