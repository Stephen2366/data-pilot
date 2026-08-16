"""M34 EnterpriseRAG 180 题的确定性 dev / held-out 分集合同。

分集只决定“哪些题可以用于调参、哪些题只能用于最终裁决”。它不包含 gold 正文，
也不参与 Knowledge Tool 运行时。required contract/security 继续由独立本地 fixture 负责。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from engine.rag.enterprise_dataset import (
    BenchmarkQuestion,
    EnterpriseDatasetError,
    canonical_identity,
)


@dataclass(frozen=True)
class EnterpriseCaseSplitRecipe:
    """用户确认的方案 A：60 dev + 120 held-out。"""

    recipe_version: str = "enterprise-rag-case-split-v1"
    diagnostic_dev_count: int = 60
    held_out_count: int = 120
    stratification: tuple[str, ...] = (
        "question_type",
        "source_signature",
        "document_cardinality",
    )


DEFAULT_CASE_SPLIT_RECIPE = EnterpriseCaseSplitRecipe()


@dataclass(frozen=True)
class EnterpriseCaseSplit:
    """轻量 question-ID manifest；题面仍以官方 questions asset 为准。"""

    recipe: EnterpriseCaseSplitRecipe
    question_set_identity: str
    diagnostic_dev_question_ids: tuple[str, ...]
    held_out_question_ids: tuple[str, ...]
    distribution: Mapping[str, Mapping[str, int]]
    split_identity: str

    def payload(self) -> dict[str, Any]:
        return {
            "recipe_version": self.recipe.recipe_version,
            "question_set_identity": self.question_set_identity,
            "stratification": list(self.recipe.stratification),
            "diagnostic_dev_question_ids": list(self.diagnostic_dev_question_ids),
            "held_out_question_ids": list(self.held_out_question_ids),
            "distribution": {
                split: dict(sorted(values.items()))
                for split, values in sorted(self.distribution.items())
            },
            "split_identity": self.split_identity,
        }


def load_enterprise_case_split(path: Path) -> EnterpriseCaseSplit:
    """加载项目内冻结 manifest；与实际 180 题的闭合校验由 validator 完成。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        recipe = EnterpriseCaseSplitRecipe(
            recipe_version=payload["recipe_version"],
            diagnostic_dev_count=len(payload["diagnostic_dev_question_ids"]),
            held_out_count=len(payload["held_out_question_ids"]),
            stratification=tuple(payload["stratification"]),
        )
        return EnterpriseCaseSplit(
            recipe=recipe,
            question_set_identity=payload["question_set_identity"],
            diagnostic_dev_question_ids=tuple(payload["diagnostic_dev_question_ids"]),
            held_out_question_ids=tuple(payload["held_out_question_ids"]),
            distribution={
                split: {key: int(value) for key, value in values.items()}
                for split, values in payload["distribution"].items()
            },
            split_identity=payload["split_identity"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnterpriseDatasetError("invalid_case_split_manifest", str(exc)) from exc


def _stratum(question: BenchmarkQuestion) -> tuple[str, str, str]:
    """提取 split 的题型、来源和单/多文档分层键。"""
    source_signature = "+".join(question.source_types)
    cardinality = "multi_document" if len(question.expected_document_ids) > 1 else "single_document"
    return question.question_type, source_signature, cardinality


def _rank(question_set_identity: str, question_id: str) -> str:
    """用冻结 question identity 生成与遍历顺序无关的稳定排序键。"""
    return sha256(f"{question_set_identity}:{question_id}".encode("utf-8")).hexdigest()


def _allocate_dev_counts(
    grouped: Mapping[tuple[str, str, str], Sequence[BenchmarkQuestion]],
    dev_count: int,
    total_count: int,
) -> dict[tuple[str, str, str], int]:
    """使用最大余数法分配名额，避免遍历顺序影响小 strata。"""

    allocations: dict[tuple[str, str, str], int] = {}
    remainders: list[tuple[float, tuple[str, str, str]]] = []
    assigned = 0
    for key in sorted(grouped):
        exact = len(grouped[key]) * dev_count / total_count
        floor = int(exact)
        allocations[key] = floor
        assigned += floor
        remainders.append((exact - floor, key))
    for _, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[
        : dev_count - assigned
    ]:
        allocations[key] += 1
    return allocations


def _distribution(
    questions: Iterable[BenchmarkQuestion], prefix: str
) -> dict[str, int]:
    """统计一个 split 的题型、来源和文档基数分布。"""
    counts: Counter[str] = Counter()
    for question in questions:
        counts[f"{prefix}:total"] += 1
        counts[f"{prefix}:type:{question.question_type}"] += 1
        counts[f"{prefix}:source:{'+'.join(question.source_types)}"] += 1
        cardinality = "multi_document" if len(question.expected_document_ids) > 1 else "single_document"
        counts[f"{prefix}:cardinality:{cardinality}"] += 1
    return dict(sorted(counts.items()))


def build_enterprise_case_split(
    questions: Sequence[BenchmarkQuestion],
    question_set_identity: str,
    recipe: EnterpriseCaseSplitRecipe = DEFAULT_CASE_SPLIT_RECIPE,
) -> EnterpriseCaseSplit:
    """在任何 retrieval 调参前冻结稳定 split。"""

    total_expected = recipe.diagnostic_dev_count + recipe.held_out_count
    if len(questions) != total_expected:
        raise EnterpriseDatasetError(
            "case_split_question_count_mismatch",
            f"expected {total_expected}, got {len(questions)}",
        )
    if not question_set_identity:
        raise EnterpriseDatasetError("case_split_identity_missing", "question_set_identity")
    ids = [question.question_id for question in questions]
    if len(set(ids)) != len(ids):
        raise EnterpriseDatasetError("case_split_duplicate_question", "input")

    grouped: defaultdict[tuple[str, str, str], list[BenchmarkQuestion]] = defaultdict(list)
    for question in questions:
        grouped[_stratum(question)].append(question)
    allocations = _allocate_dev_counts(grouped, recipe.diagnostic_dev_count, len(questions))

    dev: list[BenchmarkQuestion] = []
    held_out: list[BenchmarkQuestion] = []
    for key in sorted(grouped):
        ordered = sorted(
            grouped[key], key=lambda item: (_rank(question_set_identity, item.question_id), item.question_id)
        )
        boundary = allocations[key]
        dev.extend(ordered[:boundary])
        held_out.extend(ordered[boundary:])
    dev_ids = tuple(sorted(question.question_id for question in dev))
    held_out_ids = tuple(sorted(question.question_id for question in held_out))
    distribution = {
        "diagnostic_dev": _distribution(dev, "diagnostic_dev"),
        "held_out": _distribution(held_out, "held_out"),
    }
    unsigned = {
        "recipe_version": recipe.recipe_version,
        "question_set_identity": question_set_identity,
        "stratification": recipe.stratification,
        "diagnostic_dev_question_ids": dev_ids,
        "held_out_question_ids": held_out_ids,
        "distribution": distribution,
    }
    split = EnterpriseCaseSplit(
        recipe=recipe,
        question_set_identity=question_set_identity,
        diagnostic_dev_question_ids=dev_ids,
        held_out_question_ids=held_out_ids,
        distribution=distribution,
        split_identity=canonical_identity(unsigned),
    )
    validate_enterprise_case_split(split, questions, question_set_identity)
    return split


def validate_enterprise_case_split(
    split: EnterpriseCaseSplit,
    questions: Sequence[BenchmarkQuestion],
    question_set_identity: str,
) -> None:
    """拒绝缺题、多题、交叉、identity 或分母漂移的 manifest。"""

    dev = split.diagnostic_dev_question_ids
    held_out = split.held_out_question_ids
    if split.question_set_identity != question_set_identity:
        raise EnterpriseDatasetError("case_split_question_identity_mismatch", "manifest")
    if len(dev) != split.recipe.diagnostic_dev_count or len(held_out) != split.recipe.held_out_count:
        raise EnterpriseDatasetError("case_split_count_mismatch", "manifest")
    if len(set(dev)) != len(dev) or len(set(held_out)) != len(held_out):
        raise EnterpriseDatasetError("case_split_duplicate_question", "manifest")
    if set(dev) & set(held_out):
        raise EnterpriseDatasetError("case_split_overlap", "manifest")
    expected_ids = {question.question_id for question in questions}
    if set(dev) | set(held_out) != expected_ids:
        raise EnterpriseDatasetError("case_split_closed_world_mismatch", "manifest")
    unsigned = {
        "recipe_version": split.recipe.recipe_version,
        "question_set_identity": split.question_set_identity,
        "stratification": split.recipe.stratification,
        "diagnostic_dev_question_ids": dev,
        "held_out_question_ids": held_out,
        "distribution": split.distribution,
    }
    if canonical_identity(unsigned) != split.split_identity:
        raise EnterpriseDatasetError("case_split_hash_mismatch", "manifest")
