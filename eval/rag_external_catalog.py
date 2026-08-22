"""把 EnterpriseRAG-Bench 180 题直接投影为 M41 catalog，题面仍以原始 release 为事实源。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Literal

from engine.rag.enterprise_cases import load_enterprise_case_split, validate_enterprise_case_split
from engine.rag.enterprise_dataset import audit_enterprise_dataset, load_dataset_recipe
from eval.rag_e2e_contracts import RAGScenario, RAGScenarioCatalog, RAGSelector, canonical_hash


Partition = Literal["diagnostic_dev", "held_out", "all"]


def load_external_rag_catalog(
    *, dataset_root: Path, dataset_recipe_path: Path, split_path: Path, partition: Partition
) -> tuple[RAGScenarioCatalog, RAGSelector]:
    """完整验证 external release/split，再按冻结 ID 生成 catalog 与 selector。"""

    audit = audit_enterprise_dataset(dataset_root, load_dataset_recipe(dataset_recipe_path))
    split = load_enterprise_case_split(split_path)
    validate_enterprise_case_split(split, audit.selected_questions, audit.question_set_identity)
    dev = set(split.diagnostic_dev_question_ids)
    held_out = set(split.held_out_question_ids)
    selected_ids = {
        "diagnostic_dev": split.diagnostic_dev_question_ids,
        "held_out": split.held_out_question_ids,
        "all": tuple(item.question_id for item in audit.selected_questions),
    }[partition]
    selected_set = set(selected_ids)
    questions = {item.question_id: item for item in audit.selected_questions}
    scenarios: list[RAGScenario] = []
    for question_id in selected_ids:
        item = questions[question_id]
        scenarios.append(
            RAGScenario(
                scenario_id=item.question_id,
                classification="external_dev" if question_id in dev else "external_heldout",
                question=item.question,
                user_role="demo_user",
                expected_axes=("rag", "completed", "complete", "passed"),
                expected_reason="answer_completed",
                expected_document_keys=item.expected_document_ids,
                required_answer_terms=(),
                forbidden_public_terms=(),
                required_assertions=(
                    "route_correct", "graph_path_correct", "rag_tool_once", "retrieved_gold",
                    "selected_gold", "generation_visible_gold", "cited_gold", "answer_present",
                    "response_trace_consistent", "runtime_identity_complete", "provider_observed",
                    "composer_support_valid",
                ),
                advisory_assertions=("axes_correct", "reason_correct", "answer_facts_exact_lower_bound"),
                question_type=item.question_type,
                source_types=item.source_types,
                document_cardinality="multi_document" if len(item.expected_document_ids) > 1 else "single_document",
                gold_answer=item.gold_answer,
                answer_facts=item.answer_facts,
            )
        )
    if {item.scenario_id for item in scenarios} != selected_set:
        raise ValueError("external catalog 与冻结 partition 不闭合")
    catalog_identity = canonical_hash({
        "contract_version": "phase4-rag-external-product-v1",
        "dataset_identity": audit.dataset_identity,
        "question_set_identity": audit.question_set_identity,
        "split_identity": split.split_identity,
        "partition": partition,
        "scenarios": [asdict(item) for item in scenarios],
    })
    catalog = RAGScenarioCatalog("phase4-rag-external-product-v1", tuple(scenarios), catalog_identity)
    selector_payload = {
        "selector_id": f"external-{partition}",
        "selected_scenario_ids": selected_ids,
        "replicate_count": 1,
        "catalog_identity": catalog_identity,
    }
    selector = RAGSelector(
        selector_id=str(selector_payload["selector_id"]),
        selected_scenario_ids=tuple(selected_ids),
        replicate_count=1,
        selector_identity=canonical_hash(selector_payload),
    )
    return catalog, selector
