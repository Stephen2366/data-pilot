"""M41 补充：external difficulty、suite/partition 与 held-out 停门。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.rag.enterprise_dataset import BenchmarkQuestion
from eval.rag_e2e_contracts import RAGEvalContractError, RAGScenario, RAGScenarioCatalog, canonical_hash
from eval.rag_external_catalog import (
    EXTERNAL_RELIABILITY_IDS,
    EXTERNAL_SMOKE_IDS,
    build_external_selector,
    classify_external_difficulty,
)
from eval.rag_e2e_scoring import render_report


def _question(question_type: str, document_count: int) -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id=f"q-{question_type}-{document_count}",
        question_type=question_type,
        source_types=("jira",),
        question="question",
        expected_document_ids=tuple(f"d{index}" for index in range(document_count)),
        gold_answer="gold",
        answer_facts=("fact",),
    )


def _scenario(scenario_id: str, difficulty: str, classification: str = "external_dev") -> RAGScenario:
    return RAGScenario(
        scenario_id=scenario_id,
        classification=classification,  # type: ignore[arg-type]
        question="question",
        user_role="demo_user",
        expected_axes=("rag", "completed", "complete", "passed"),
        expected_reason="answer_completed",
        expected_document_keys=("d1",),
        required_answer_terms=(),
        forbidden_public_terms=(),
        required_assertions=("route_correct",),
        advisory_assertions=(),
        question_type="basic",
        document_cardinality="single_document",
        difficulty=difficulty,  # type: ignore[arg-type]
    )


def _catalog() -> tuple[RAGScenarioCatalog, tuple[str, ...], tuple[str, ...]]:
    dev = tuple(dict.fromkeys((*EXTERNAL_SMOKE_IDS, *EXTERNAL_RELIABILITY_IDS)))
    difficulties = ("basic", "basic", "basic", "core", "core", "core", "hard", "hard", "hard")
    scenarios = [_scenario(scenario_id, difficulties[index]) for index, scenario_id in enumerate(dev)]
    held = ("held-basic", "held-core", "held-hard")
    scenarios.extend(
        _scenario(scenario_id, difficulty, "external_heldout")
        for scenario_id, difficulty in zip(held, ("basic", "core", "hard"), strict=True)
    )
    identity = canonical_hash([item.scenario_id for item in scenarios])
    return RAGScenarioCatalog("test-external", tuple(scenarios), identity), dev, held


def test_difficulty_uses_intrinsic_question_metadata() -> None:
    assert classify_external_difficulty(_question("basic", 1)) == "basic"
    assert classify_external_difficulty(_question("semantic", 1)) == "core"
    assert classify_external_difficulty(_question("constrained", 2)) == "hard"
    assert classify_external_difficulty(_question("intra_document_reasoning", 1)) == "hard"


def test_suite_intersects_partition_and_reliability_is_a_protocol() -> None:
    catalog, dev, held = _catalog()
    assert build_external_selector(
        catalog=catalog, dev_ids=dev, held_out_ids=held, partition="diagnostic_dev", suite="smoke"
    ).selected_scenario_ids == EXTERNAL_SMOKE_IDS
    reliability = build_external_selector(
        catalog=catalog, dev_ids=dev, held_out_ids=held, partition="diagnostic_dev", suite="reliability"
    )
    assert reliability.selected_scenario_ids == EXTERNAL_RELIABILITY_IDS
    assert reliability.replicate_count == 3
    hard_held = build_external_selector(
        catalog=catalog, dev_ids=dev, held_out_ids=held, partition="held_out", suite="hard"
    )
    assert hard_held.selected_scenario_ids == ("held-hard",)


def test_smoke_cannot_be_repointed_to_held_out() -> None:
    catalog, dev, held = _catalog()
    with pytest.raises(RAGEvalContractError, match="冻结 dev 套件"):
        build_external_selector(
            catalog=catalog, dev_ids=dev, held_out_ids=held, partition="held_out", suite="smoke"
        )


def test_external_report_uses_selected_difficulty_outcomes_not_full_catalog_counts() -> None:
    hard = replace(_scenario("hard-selected", "hard"), question_type="completeness")
    unselected = replace(_scenario("basic-unselected", "basic"), question_type="basic")
    artifact = {
        "run_spec": {"run_id": "report-test", "selected_scenario_ids": ["hard-selected"]},
        "artifact_identity": "artifact",
        "gate": {"status": "failed", "passed": 0, "failed": 1, "not_observed": 0},
        "executions": [{
            "scenario_id": "hard-selected", "replicate": 1,
            "route": "rag", "execution_status": "completed", "answer_status": "complete",
            "safety_status": "passed",
            "stage_counts": [["candidate", 1], ["selected", 1], ["generation_visible", 1], ["cited", 0]],
        }],
        "assertions": [{
            "scenario_id": "hard-selected", "replicate": 1, "assertion_id": "retrieved_gold",
            "effect": "required", "status": "failed", "reason": "missing", "evidence_ref": "e",
        }],
    }
    report = render_report(
        artifact=artifact,
        scenarios={"hard-selected": hard, "basic-unselected": unselected},
        triage=({"scenario_id": "hard-selected", "replicate": 1, "primary_stage": "retrieval"},),
    )
    assert "difficulty:hard | 1 | retrieval=1" in report
    assert "difficulty:basic" not in report
