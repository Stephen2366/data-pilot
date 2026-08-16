"""M34 Answer Eval 的 gold 后置评分与 completed artifact 门。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from engine.governance import test_caller as make_test_caller
from engine.rag.answer_flow import RAGAnswerFlow, RAGAnswerRequest
from engine.rag.enterprise_answer_eval import build_answer_execution, finalize_answer_artifact
from engine.rag.enterprise_dataset import BenchmarkQuestion, EnterpriseDatasetError
from engine.rag.evidence import DocumentContextCoordinates
from engine.rag.retrieval import RetrievalBudget


def _question() -> BenchmarkQuestion:
    return BenchmarkQuestion(
        question_id="q-test",
        question_type="basic",
        source_types=("confluence",),
        question="质量问题退款需要什么材料？",
        expected_document_ids=("not-the-runtime-document",),
        gold_answer="需要证明材料。",
        answer_facts=("需要证明材料",),
    )


def _add_external_coordinates(result):
    """业务 fixture 没有大 corpus 坐标；只在测试中补成 external Evidence 形状。"""

    evidence = tuple(
        replace(
            item,
            payload=replace(
                item.payload,
                context_coordinates=DocumentContextCoordinates(
                    source_type="confluence",
                    logical_document_id="runtime-document",
                    physical_source_identity="physical",
                    unit_identity="unit",
                    normalized_start=0,
                    normalized_end=len(item.payload.content),
                ),
            ),
        )
        for item in result.ledger.evidence
    )
    return replace(result, ledger=replace(result.ledger, evidence=evidence))


def test_execution_scores_only_real_result_and_does_not_confuse_citation_with_gold() -> None:
    result = RAGAnswerFlow().run(
        RAGAnswerRequest(
            question="质量问题退款需要什么材料？",
            caller=make_test_caller(caller_id="answer-eval", roles={"customer_service"}),
            run_id="m34-answer-eval-fixture",
            retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=1),
        )
    )
    execution = build_answer_execution(
        question=_question(),
        result=_add_external_coordinates(result),
        contract_error=None,
        provider_usage_delta={"request_count": 0, "total_tokens": 0},
        composer_attempt=None,
    )

    assert execution["answer_flow_calls"] == 1
    assert execution["result"]["answer_status"] == "complete"
    assert execution["document_coverage"]["all_gold"] is False
    assert execution["exact_fact_coverage"] == 0.0


def test_completed_artifact_rejects_missing_duplicate_or_extra_question() -> None:
    result = RAGAnswerFlow().run(
        RAGAnswerRequest(
            question="质量问题退款需要什么材料？",
            caller=make_test_caller(caller_id="answer-eval", roles={"customer_service"}),
            run_id="m34-answer-eval-closed-world",
            retrieval_budget=RetrievalBudget(max_candidates=5, max_selected=1),
        )
    )
    execution = build_answer_execution(
        question=_question(),
        result=_add_external_coordinates(result),
        contract_error=None,
        provider_usage_delta={},
        composer_attempt=None,
    )
    artifact = finalize_answer_artifact(
        dataset_identity="dataset",
        question_set_identity="questions",
        split_identity="split",
        profile_identity="profile",
        composer_identity="composer",
        question_ids=("q-test",),
        executions=(execution,),
    )
    assert artifact["status"] == "completed" and artifact["question_count"] == 1

    with pytest.raises(EnterpriseDatasetError, match="answer_eval_closed_world_mismatch"):
        finalize_answer_artifact(
            dataset_identity="dataset",
            question_set_identity="questions",
            split_identity="split",
            profile_identity="profile",
            composer_identity="composer",
            question_ids=("q-test", "q-other"),
            executions=(execution,),
        )
    with pytest.raises(EnterpriseDatasetError, match="answer_eval_flow_call_mismatch"):
        finalize_answer_artifact(
            dataset_identity="dataset",
            question_set_identity="questions",
            split_identity="split",
            profile_identity="profile",
            composer_identity="composer",
            question_ids=("q-test",),
            executions=({**execution, "answer_flow_calls": 2},),
        )
