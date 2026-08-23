"""把 EnterpriseRAG-Bench 180 题投影为 canonical catalog 与可组合运行套件。

题面、gold 和 dev/held-out 仍由 immutable release/split 提供；本文件只增加稳定的
``difficulty`` 与 selector 规则，不复制第二份题库。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Literal, Sequence

from engine.rag.enterprise_cases import load_enterprise_case_split, validate_enterprise_case_split
from engine.rag.enterprise_dataset import BenchmarkQuestion, audit_enterprise_dataset, load_dataset_recipe
from eval.rag_e2e_contracts import (
    RAGEvalContractError,
    RAGScenario,
    RAGScenarioCatalog,
    RAGSelector,
    canonical_hash,
)


Partition = Literal["diagnostic_dev", "held_out", "all"]
ExternalSuite = Literal["smoke", "basic", "core", "hard", "reliability", "full"]
Difficulty = Literal["basic", "core", "hard"]

# Smoke 是日常低成本产品体检：三档各 3 题，并覆盖三种单来源、跨来源冲突、
# completeness 与 intra-document reasoning。只保存 ID，不复制题面。
EXTERNAL_SMOKE_IDS = (
    "qst_0016", "qst_0047", "qst_0019",
    "qst_0386", "qst_0461", "qst_0181",
    "qst_0420", "qst_0431", "qst_0318",
)
# Reliability 是执行协议，不是第四种难度：每档 2 题、每题重复 3 次。
EXTERNAL_RELIABILITY_IDS = (
    "qst_0016", "qst_0047",
    "qst_0386", "qst_0181",
    "qst_0420", "qst_0318",
)
EXPECTED_DIFFICULTY_COUNTS = {"basic": 64, "core": 74, "hard": 42}


def classify_external_difficulty(question: BenchmarkQuestion) -> Difficulty:
    """只按运行前可见的题目属性分层，禁止用当前模型表现反向定义难度。"""

    multi_document = len(question.expected_document_ids) > 1
    advanced_types = {
        "completeness", "conflicting_info", "intra_document_reasoning", "project_related",
    }
    if multi_document or question.question_type in advanced_types:
        return "hard"
    if question.question_type == "basic":
        return "basic"
    return "core"


def build_external_selector(
    *,
    catalog: RAGScenarioCatalog,
    dev_ids: Sequence[str],
    held_out_ids: Sequence[str],
    partition: Partition,
    suite: ExternalSuite,
) -> RAGSelector:
    """对 canonical 180 catalog 做 ``partition × suite`` 交集，不复制 Scenario。"""

    by_id = catalog.by_id()
    partition_ids = {
        "diagnostic_dev": tuple(dev_ids),
        "held_out": tuple(held_out_ids),
        "all": tuple(item.scenario_id for item in catalog.scenarios),
    }[partition]
    if suite in {"smoke", "reliability"} and partition != "diagnostic_dev":
        raise RAGEvalContractError(
            "rag_external_suite_partition_invalid",
            f"{suite} 是冻结 dev 套件；不得改指向 {partition}",
        )
    if suite == "smoke":
        selected = EXTERNAL_SMOKE_IDS
        replicate_count = 1
    elif suite == "reliability":
        selected = EXTERNAL_RELIABILITY_IDS
        replicate_count = 3
    elif suite in {"basic", "core", "hard"}:
        selected = tuple(question_id for question_id in partition_ids if by_id[question_id].difficulty == suite)
        replicate_count = 1
    else:
        selected = partition_ids
        replicate_count = 1
    if not selected or len(selected) != len(set(selected)):
        raise RAGEvalContractError("rag_external_selector_invalid", "suite 为空或题目重复")
    if not set(selected).issubset(set(partition_ids)) or not set(selected).issubset(by_id):
        raise RAGEvalContractError("rag_external_selector_invalid", "suite 越过 partition 或含未知题")
    selector_payload = {
        "selector_id": f"external-{partition}-{suite}",
        "selected_scenario_ids": selected,
        "replicate_count": replicate_count,
        "catalog_identity": catalog.catalog_identity,
    }
    return RAGSelector(
        selector_id=str(selector_payload["selector_id"]),
        selected_scenario_ids=tuple(selected),
        replicate_count=replicate_count,
        selector_identity=canonical_hash(selector_payload),
    )


def build_external_scenario_selector(
    *,
    catalog: RAGScenarioCatalog,
    partition: Partition,
    scenario_id: str,
) -> RAGSelector:
    """构造单题产品 smoke；仍严格受 partition 约束，不能借 ID 偷看 held-out。"""

    scenario = catalog.by_id().get(scenario_id)
    if scenario is None:
        raise RAGEvalContractError("rag_external_selector_invalid", "未知 Scenario")
    allowed = (
        partition == "all"
        or (partition == "diagnostic_dev" and scenario.classification == "external_dev")
        or (partition == "held_out" and scenario.classification == "external_heldout")
    )
    if not allowed:
        raise RAGEvalContractError(
            "rag_external_selector_partition_invalid",
            "Scenario 不属于当前显式 partition",
        )
    payload = {
        "selector_id": f"external-{partition}-scenario-{scenario_id}",
        "selected_scenario_ids": (scenario_id,),
        "replicate_count": 1,
        "catalog_identity": catalog.catalog_identity,
    }
    return RAGSelector(
        selector_id=str(payload["selector_id"]),
        selected_scenario_ids=(scenario_id,),
        replicate_count=1,
        selector_identity=canonical_hash(payload),
    )


def load_external_rag_catalog(
    *,
    dataset_root: Path,
    dataset_recipe_path: Path,
    split_path: Path,
    partition: Partition,
    suite: ExternalSuite = "full",
) -> tuple[RAGScenarioCatalog, RAGSelector]:
    """验证 immutable release/split，构建同一个 180 题 catalog 后再选择运行范围。"""

    audit = audit_enterprise_dataset(dataset_root, load_dataset_recipe(dataset_recipe_path))
    split = load_enterprise_case_split(split_path)
    validate_enterprise_case_split(split, audit.selected_questions, audit.question_set_identity)
    dev = set(split.diagnostic_dev_question_ids)
    scenarios: list[RAGScenario] = []
    for item in audit.selected_questions:
        scenarios.append(
            RAGScenario(
                scenario_id=item.question_id,
                classification="external_dev" if item.question_id in dev else "external_heldout",
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
                document_cardinality=(
                    "multi_document" if len(item.expected_document_ids) > 1 else "single_document"
                ),
                difficulty=classify_external_difficulty(item),
                gold_answer=item.gold_answer,
                answer_facts=item.answer_facts,
            )
        )
    if len(scenarios) != 180 or {item.scenario_id for item in scenarios} != {
        item.question_id for item in audit.selected_questions
    }:
        raise RAGEvalContractError("rag_external_catalog_invalid", "canonical catalog 未闭合 180 题")
    difficulty_counts = Counter(item.difficulty for item in scenarios)
    if dict(difficulty_counts) != EXPECTED_DIFFICULTY_COUNTS:
        raise RAGEvalContractError(
            "rag_external_difficulty_drift",
            f"expected={EXPECTED_DIFFICULTY_COUNTS}, actual={dict(difficulty_counts)}",
        )
    catalog_identity = canonical_hash({
        "contract_version": "phase4-rag-external-product-v2",
        "dataset_identity": audit.dataset_identity,
        "question_set_identity": audit.question_set_identity,
        "split_identity": split.split_identity,
        "difficulty_recipe": "enterprise-rag-difficulty-v1",
        "scenarios": [asdict(item) for item in scenarios],
    })
    catalog = RAGScenarioCatalog("phase4-rag-external-product-v2", tuple(scenarios), catalog_identity)
    selector = build_external_selector(
        catalog=catalog,
        dev_ids=split.diagnostic_dev_question_ids,
        held_out_ids=split.held_out_question_ids,
        partition=partition,
        suite=suite,
    )
    return catalog, selector
