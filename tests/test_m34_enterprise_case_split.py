"""M34 60/120 分集的确定性、分层和 closed-world 合同。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.rag.enterprise_dataset import BenchmarkQuestion, EnterpriseDatasetError
from engine.rag.enterprise_cases import (
    build_enterprise_case_split,
    validate_enterprise_case_split,
)


def _questions() -> tuple[BenchmarkQuestion, ...]:
    questions = []
    types = ("basic", "semantic", "constrained")
    sources = (("confluence",), ("google_drive",), ("jira",), ("confluence", "jira"))
    for index in range(180):
        multi = index % 5 == 0
        questions.append(
            BenchmarkQuestion(
                question_id=f"qst_{index:04d}",
                question_type=types[index % len(types)],
                source_types=sources[index % len(sources)],
                question=f"Question {index}",
                expected_document_ids=("doc-a", "doc-b") if multi else ("doc-a",),
                gold_answer=f"Answer {index}",
                answer_facts=(f"Fact {index}",),
            )
        )
    return tuple(questions)


def test_scheme_a_is_deterministic_disjoint_and_closed_world() -> None:
    questions = _questions()
    first = build_enterprise_case_split(questions, "questions-v1")
    second = build_enterprise_case_split(tuple(reversed(questions)), "questions-v1")

    assert first == second
    assert len(first.diagnostic_dev_question_ids) == 60
    assert len(first.held_out_question_ids) == 120
    assert not set(first.diagnostic_dev_question_ids) & set(first.held_out_question_ids)
    assert set(first.diagnostic_dev_question_ids) | set(first.held_out_question_ids) == {
        item.question_id for item in questions
    }
    assert first.distribution["diagnostic_dev"]["diagnostic_dev:type:semantic"] == 20
    assert first.distribution["held_out"]["held_out:type:semantic"] == 40


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("identity", "case_split_question_identity_mismatch"),
        ("count", "case_split_count_mismatch"),
        ("overlap", "case_split_overlap"),
        ("hash", "case_split_hash_mismatch"),
    ],
)
def test_split_validation_rejects_tampering(mutation: str, reason_code: str) -> None:
    questions = _questions()
    split = build_enterprise_case_split(questions, "questions-v1")
    if mutation == "identity":
        split = replace(split, question_set_identity="other")
    elif mutation == "count":
        split = replace(
            split, diagnostic_dev_question_ids=split.diagnostic_dev_question_ids[:-1]
        )
    elif mutation == "overlap":
        held_out = list(split.held_out_question_ids)
        held_out[0] = split.diagnostic_dev_question_ids[0]
        split = replace(split, held_out_question_ids=tuple(held_out))
    else:
        split = replace(split, split_identity="tampered")

    with pytest.raises(EnterpriseDatasetError) as captured:
        validate_enterprise_case_split(split, questions, "questions-v1")
    assert captured.value.reason_code == reason_code
