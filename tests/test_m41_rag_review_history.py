"""M41 review 来源、严格 compare 与 M34 historical 只读边界。"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine.rag.enterprise_answer_eval import finalize_answer_artifact
from engine.rag.enterprise_dataset import canonical_identity
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
    assert verify_review_sources(bundle) == {"artifact": 1, "checkpoints": 5}

    checkpoint = Path(bundle["records"][0]["source_checkpoint"]["path"])
    checkpoint.write_text(checkpoint.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(RAGEvalContractError, match="hash"):
        verify_review_sources(bundle)


def test_compare_accepts_only_identical_protocol_and_runtime(tmp_path: Path) -> None:
    left = _run(tmp_path)
    right = deepcopy(left)
    right["run_spec"]["run_id"] = "m41-test-business-right"
    _resign(right)
    assert compare_completed(left, right)["strictly_comparable"] is True

    right["run_spec"]["runtime"]["model"] = "different-model"
    _resign(right)
    with pytest.raises(RAGEvalContractError, match="not_comparable|identity"):
        compare_completed(left, right)

    candidate = compare_completed(left, right, allowed_runtime_differences=("model",))
    assert candidate["comparison_mode"] == "candidate"
    assert candidate["strictly_comparable"] is False
    assert candidate["experiment_contract"]["actual_runtime_differences"] == ["model"]
    assert candidate["paired_summary"] == {"tie": 5}
    assert "provider_usage" in candidate and "answer_flow_latency" in candidate


def test_candidate_compare_reports_paired_regression_and_rejects_unknown_allowlist(tmp_path: Path) -> None:
    left = _run(tmp_path)
    right = deepcopy(left)
    right["run_spec"]["run_id"] = "m41-test-candidate"
    right["run_spec"]["runtime"]["model"] = "candidate-model"
    target = next(
        item for item in right["assertions"]
        if item["scenario_id"] == "quality_refund_materials"
        and item["effect"] == "required"
        and item["status"] == "passed"
    )
    target["status"] = "failed"
    target["reason"] = "simulated regression"
    required = [item["status"] for item in right["assertions"] if item["effect"] == "required"]
    right["gate"] = {
        "status": "failed",
        "passed": required.count("passed"),
        "failed": required.count("failed"),
        "not_observed": required.count("not_observed"),
    }
    _resign(right)

    result = compare_completed(left, right, allowed_runtime_differences=("model",))
    assert result["paired_summary"] == {"loss": 1, "tie": 4}
    assert any(item["verdict"] == "loss" for item in result["paired_executions"])
    with pytest.raises(RAGEvalContractError, match="未知 runtime 字段"):
        compare_completed(left, right, allowed_runtime_differences=("not_a_runtime_field",))


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


def test_m34_importer_projects_all_cases_with_retrieval_and_split_strata(tmp_path: Path) -> None:
    execution = {
        "question_id": "q1", "question_type": "semantic", "source_types": ["jira"],
        "document_cardinality": "single_document", "expected_document_ids": ["d1"],
        "gold_answer": "gold", "answer_facts": ["gold"], "outcome": "answer_result",
        "internal_reason_code": "answer_completed",
        "result": {"answer_status": "complete", "diagnostics": {"elapsed_ms": 1}},
        "cited_logical_document_ids": ["d1"],
        "document_coverage": {"covered": 1, "expected": 1, "coverage": 1.0, "all_gold": True},
        "fact_checks": [{"fact": "gold", "exactly_supported": True}], "exact_fact_coverage": 1.0,
        "provider_usage_delta": {"request_count": 1, "total_tokens": 10},
        "composer_attempt": {"status": "succeeded"}, "answer_flow_calls": 1,
    }
    artifact = finalize_answer_artifact(
        dataset_identity="dataset", question_set_identity="questions", split_identity="split",
        profile_identity="profile", composer_identity="composer", question_ids=("q1",), executions=(execution,),
    )
    answer_path = tmp_path / "answer.json"
    answer_path.write_text(json.dumps(artifact), encoding="utf-8")
    retrieval_execution = {
        "question_id": "q1", "adapter_calls": 1, "actual_matches": [{"logical_document_id": "d1"}],
        "coverage": {"20": {"covered": 1, "expected": 1, "coverage": 1.0, "all_gold": True}},
    }
    retrieval_identity = {
        "format": "enterprise-rag-retrieval-eval-v1", "dataset_identity": "dataset",
        "question_set_identity": "questions", "split_identity": "split", "split_name": "diagnostic_dev",
        "profile_identity": "profile", "adapter_identity": "adapter", "retrieval_recipe_identity": "recipe",
        "executions": [retrieval_execution],
    }
    retrieval = {
        **{key: value for key, value in retrieval_identity.items() if key != "executions"},
        "status": "completed", "question_count": 1, "tool_call_count": 1,
        "artifact_identity": canonical_identity(retrieval_identity), "executions": [retrieval_execution],
    }
    retrieval_path = tmp_path / "retrieval.json"
    retrieval_path.write_text(json.dumps(retrieval), encoding="utf-8")
    split = {
        "question_set_identity": "questions", "split_identity": "split",
        "diagnostic_dev_question_ids": ["q1"], "held_out_question_ids": [],
    }
    split_path = tmp_path / "split.json"
    split_path.write_text(json.dumps(split), encoding="utf-8")

    view = import_m34_answer_history(
        answer_path, retrieval_paths=(retrieval_path,), split_manifest_path=split_path
    )

    assert view["format"] == "phase4-rag-m34-historical-view-v2"
    assert view["cases"][0]["partition"] == "diagnostic_dev"
    assert view["cases"][0]["layers"]["retrieval"]["status"] == "passed"
    assert view["cases"][0]["layers"]["product_api_router_harness_trace"]["status"] == "not_observed"
