"""在真实 external candidate 上证明 Tool → Evidence → AnswerFlow → citation 链路。

默认只从冻结 diagnostic/dev 中确定性选择 semantic、multi-document 和普通题各一题。
gold 只在整次 AnswerFlow 返回后用于离线覆盖统计，绝不传给 runtime。
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from time import perf_counter

from engine.governance import demo_caller
from engine.rag.answer_flow import RAGAnswerRequest
from engine.rag.enterprise_cases import (
    load_enterprise_case_split,
    validate_enterprise_case_split,
)
from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from engine.rag.enterprise_runtime import load_enterprise_profile_runtime
from engine.rag.evidence import DocumentEvidencePayload
from engine.rag.retrieval import RetrievalBudget

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_RECIPE = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-dataset.json"
)
DEFAULT_SPLIT = (
    PROJECT_ROOT / "eval" / "cases" / "enterprise-rag-bench-v1.0.0-split.json"
)


def _choose_question_ids(audit, split) -> tuple[str, ...]:
    """固定选择三类 dev smoke，不查看 retrieval 分数或 gold 正文。"""

    allowed = set(split.diagnostic_dev_question_ids)
    questions = [item for item in audit.selected_questions if item.question_id in allowed]
    semantic = next(item for item in questions if item.question_type == "semantic")
    multi = next(
        item
        for item in questions
        if len(item.expected_document_ids) > 1 and item.question_id != semantic.question_id
    )
    ordinary = next(
        item
        for item in questions
        if item.question_type != "semantic"
        and len(item.expected_document_ids) == 1
        and item.question_id not in {semantic.question_id, multi.question_id}
    )
    return semantic.question_id, multi.question_id, ordinary.question_id


def _coverage(expected: tuple[str, ...], actual: tuple[str, ...]) -> dict[str, object]:
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    covered = sum(min(count, actual_counts[key]) for key, count in expected_counts.items())
    return {
        "covered": covered,
        "expected": len(expected),
        "coverage": covered / len(expected),
        "all_gold": covered == len(expected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root", type=Path, default=os.environ.get("ENTERPRISE_RAG_BENCH_ROOT")
    )
    parser.add_argument("--dataset-recipe", type=Path, default=DEFAULT_DATASET_RECIPE)
    parser.add_argument("--case-split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--profile-root", type=Path)
    parser.add_argument("--profile-identity", required=True)
    parser.add_argument("--question-id", action="append", dest="question_ids")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.dataset_root is None:
        raise SystemExit("必须提供 --dataset-root 或 ENTERPRISE_RAG_BENCH_ROOT")
    profile_root = args.profile_root or args.dataset_root / "derived" / "enterprise_profiles"

    audit = audit_enterprise_dataset(
        args.dataset_root, load_dataset_recipe(args.dataset_recipe)
    )
    split = load_enterprise_case_split(args.case_split)
    validate_enterprise_case_split(split, audit.selected_questions, audit.question_set_identity)
    question_by_id = {item.question_id: item for item in audit.selected_questions}
    question_ids = tuple(args.question_ids or _choose_question_ids(audit, split))
    if not question_ids or len(set(question_ids)) != len(question_ids):
        raise SystemExit("question IDs 不能为空或重复")
    if not set(question_ids) <= set(split.diagnostic_dev_question_ids):
        raise SystemExit("smoke 只允许冻结的 diagnostic/dev question IDs")

    started = perf_counter()
    executions: list[dict[str, object]] = []
    with load_enterprise_profile_runtime(
        root=profile_root, profile_identity=args.profile_identity
    ) as runtime:
        flow = runtime.answer_flow()
        for ordinal, question_id in enumerate(question_ids, start=1):
            question = question_by_id[question_id]
            result = flow.run(
                RAGAnswerRequest(
                    question=question.question,
                    caller=demo_caller(caller_id="m34-runtime-smoke", roles=("demo_user",)),
                    run_id=f"m34-runtime-smoke-{ordinal:02d}-{question_id}",
                    retrieval_budget=RetrievalBudget(max_candidates=10, max_selected=3),
                )
            )
            context = (
                result.gate_decision.context.evidence
                if result.gate_decision is not None and result.gate_decision.context is not None
                else ()
            )
            coordinates = tuple(
                item.payload.context_coordinates
                for item in context
                if isinstance(item.payload, DocumentEvidencePayload)
                and item.payload.context_coordinates is not None
            )
            actual_logical_ids = tuple(item.logical_document_id for item in coordinates)
            executions.append(
                {
                    "question_id": question_id,
                    "question_type": question.question_type,
                    "expected_document_count": len(question.expected_document_ids),
                    "result": result.safe_projection(),
                    "actual_context": [
                        {
                            "source_type": item.source_type,
                            "logical_document_id": item.logical_document_id,
                            "physical_source_identity": item.physical_source_identity,
                            "unit_identity": item.unit_identity,
                            "normalized_start": item.normalized_start,
                            "normalized_end": item.normalized_end,
                        }
                        for item in coordinates
                    ],
                    "gold_coverage_after_run": _coverage(
                        question.expected_document_ids, actual_logical_ids
                    ),
                }
            )
        payload = {
            "format": "m34-external-runtime-smoke-v1",
            "status": "completed",
            "dataset_identity": audit.dataset_identity,
            "question_set_identity": audit.question_set_identity,
            "split_identity": split.split_identity,
            "profile_identity": runtime.manifest.profile_identity,
            "profile_lifecycle": runtime.selection.lifecycle_status,
            "adapter_identity": runtime.adapter.identity,
            "retrieval_recipe_identity": runtime.adapter.recipe_identity,
            "question_count": len(executions),
            "elapsed_seconds": round(perf_counter() - started, 6),
            "executions": executions,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: payload[key] for key in payload if key != "executions"}, indent=2))


if __name__ == "__main__":
    main()
