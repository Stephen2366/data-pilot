"""从规范化文档构建稳定、可回查的 retrieval/context unit 候选。

本模块只提供参数化构建器，不宣布最终 chunk 默认。M34-B 会先比较候选的行数、长度、
重复字符和 gold 文档局部性；最终 recipe 仍需在冻结 dev split 上用检索证据确认。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from engine.rag.enterprise_dataset import DatasetAudit, EnterpriseDatasetError, canonical_identity
from engine.rag.enterprise_parser import (
    DEFAULT_PARSER_RECIPE,
    NormalizedDocument,
    ParserRecipe,
    iter_normalized_documents,
)


@dataclass(frozen=True)
class UnitRecipe:
    """单变量可比较的 unit 构建 recipe。"""

    recipe_version: str
    strategy: str
    max_characters: int | None = None
    overlap_paragraphs: int = 0

    @property
    def identity(self) -> str:
        return canonical_identity(
            {
                "recipe_version": self.recipe_version,
                "strategy": self.strategy,
                "max_characters": self.max_characters,
                "overlap_paragraphs": self.overlap_paragraphs,
            }
        )


WHOLE_DOCUMENT_RECIPE = UnitRecipe(
    recipe_version="enterprise-unit-whole-document-v1",
    strategy="whole_document",
)
PARAGRAPH_1200_RECIPE = UnitRecipe(
    recipe_version="enterprise-unit-paragraph-1200-v1",
    strategy="paragraph_pack",
    max_characters=1200,
)
PARAGRAPH_2400_RECIPE = UnitRecipe(
    recipe_version="enterprise-unit-paragraph-2400-v1",
    strategy="paragraph_pack",
    max_characters=2400,
)
PARAGRAPH_2400_OVERLAP_1_RECIPE = UnitRecipe(
    recipe_version="enterprise-unit-paragraph-2400-overlap1-v1",
    strategy="paragraph_pack",
    max_characters=2400,
    overlap_paragraphs=1,
)


@dataclass(frozen=True)
class RetrievalUnit:
    """offset anchor 指向 normalized revision，而非不稳定的遍历序号。"""

    unit_identity: str
    document_revision: str
    physical_source_identity: str
    logical_document_id: str
    source_type: str
    normalized_start: int
    normalized_end: int
    anchor: str
    content: str
    content_sha256: str
    recipe_identity: str


def _paragraph_spans(content: str) -> list[tuple[int, int]]:
    """返回非空段落的原始字符区间，段间空白留在相邻 packed unit 内。"""

    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"[^\s].*?(?=\n[ \t]*\n|\Z)", content, flags=re.DOTALL):
        start, end = match.span()
        while end > start and content[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))
    return spans


def _split_oversized_span(
    content: str, span: tuple[int, int], max_characters: int
) -> list[tuple[int, int]]:
    """优先在行尾切超长段，找不到时才硬切；所有 offset 仍指向原文。"""

    start, end = span
    parts: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_characters:
        ceiling = cursor + max_characters
        line_break = content.rfind("\n", cursor + 1, ceiling + 1)
        cut = line_break if line_break > cursor else ceiling
        parts.append((cursor, cut))
        cursor = cut
        while cursor < end and content[cursor] == "\n":
            cursor += 1
    if cursor < end:
        parts.append((cursor, end))
    return parts


def _pack_spans(
    content: str, spans: list[tuple[int, int]], recipe: UnitRecipe
) -> list[tuple[int, int]]:
    max_characters = recipe.max_characters
    if max_characters is None or max_characters <= 0:
        raise EnterpriseDatasetError("invalid_unit_recipe", recipe.recipe_version)
    if recipe.overlap_paragraphs < 0:
        raise EnterpriseDatasetError("invalid_unit_recipe", recipe.recipe_version)

    atoms: list[tuple[int, int]] = []
    for span in spans:
        atoms.extend(_split_oversized_span(content, span, max_characters))
    if not atoms:
        return []

    packed: list[tuple[int, int]] = []
    window: list[tuple[int, int]] = []
    for atom in atoms:
        if window and atom[1] - window[0][0] > max_characters:
            packed.append((window[0][0], window[-1][1]))
            retained = window[-recipe.overlap_paragraphs :] if recipe.overlap_paragraphs else []
            window = list(retained)
            # 一个接近上限的 retained atom 不能阻止新 atom 前进。
            if window and atom[1] - window[0][0] > max_characters:
                window = []
        window.append(atom)
    if window:
        packed.append((window[0][0], window[-1][1]))
    return packed


def build_retrieval_units(
    document: NormalizedDocument, recipe: UnitRecipe
) -> tuple[RetrievalUnit, ...]:
    """构建 units，并立即验证 offset/content/identity 闭合。"""

    if recipe.strategy == "whole_document":
        spans = [(0, len(document.content))]
    elif recipe.strategy == "paragraph_pack":
        spans = _pack_spans(document.content, _paragraph_spans(document.content), recipe)
    else:
        raise EnterpriseDatasetError("unsupported_unit_strategy", recipe.strategy)
    if not spans:
        raise EnterpriseDatasetError(
            "empty_unit_build", document.source_instance.relative_path
        )

    units: list[RetrievalUnit] = []
    for start, end in spans:
        if start < 0 or end > len(document.content) or start >= end:
            raise EnterpriseDatasetError("unit_offset_invalid", document.document_revision)
        content = document.content[start:end]
        content_hash = sha256(content.encode("utf-8")).hexdigest()
        anchor = f"normalized-char:{start}-{end}"
        unit_identity = canonical_identity(
            {
                "document_revision": document.document_revision,
                "recipe_identity": recipe.identity,
                "normalized_start": start,
                "normalized_end": end,
                "content_sha256": content_hash,
            }
        )
        units.append(
            RetrievalUnit(
                unit_identity=unit_identity,
                document_revision=document.document_revision,
                physical_source_identity=document.source_instance.physical_identity,
                logical_document_id=document.source_instance.logical_document_id,
                source_type=document.source_instance.source_type,
                normalized_start=start,
                normalized_end=end,
                anchor=anchor,
                content=content,
                content_sha256=content_hash,
                recipe_identity=recipe.identity,
            )
        )
    if len({unit.unit_identity for unit in units}) != len(units):
        raise EnterpriseDatasetError("duplicate_unit_identity", document.document_revision)
    return tuple(units)


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * percentile)]


def profile_unit_candidates(
    audit: DatasetAudit,
    recipes: Iterable[UnitRecipe],
    parser_recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
) -> dict[str, Any]:
    """同一 parser/corpus 上比较 unit 规模与上下文成本，不做效果裁决。"""

    recipe_list = tuple(recipes)
    if len({recipe.identity for recipe in recipe_list}) != len(recipe_list):
        raise EnterpriseDatasetError("duplicate_unit_recipe", "candidate identities")
    accumulators: dict[str, dict[str, Any]] = {
        recipe.recipe_version: {
            "recipe": recipe,
            "unit_lengths": [],
            "units_per_document": [],
            "total_unit_characters": 0,
            "gold_units_per_document": [],
        }
        for recipe in recipe_list
    }
    gold_ids = {
        document_id
        for question in audit.selected_questions
        for document_id in question.expected_document_ids
    }
    normalized_characters = 0
    for document in iter_normalized_documents(audit, parser_recipe):
        normalized_characters += len(document.content)
        for recipe in recipe_list:
            units = build_retrieval_units(document, recipe)
            bucket = accumulators[recipe.recipe_version]
            lengths = [len(unit.content) for unit in units]
            bucket["unit_lengths"].extend(lengths)
            bucket["units_per_document"].append(len(units))
            bucket["total_unit_characters"] += sum(lengths)
            if document.source_instance.logical_document_id in gold_ids:
                bucket["gold_units_per_document"].append(len(units))

    results: dict[str, Any] = {}
    for version, bucket in accumulators.items():
        recipe = bucket["recipe"]
        lengths = bucket["unit_lengths"]
        per_document = bucket["units_per_document"]
        gold_per_document = bucket["gold_units_per_document"]
        results[version] = {
            "recipe_identity": recipe.identity,
            "strategy": recipe.strategy,
            "max_characters": recipe.max_characters,
            "overlap_paragraphs": recipe.overlap_paragraphs,
            "unit_count": len(lengths),
            "unit_character_length": {
                "p50": _percentile(lengths, 0.50),
                "p95": _percentile(lengths, 0.95),
                "p99": _percentile(lengths, 0.99),
                "max": max(lengths, default=0),
            },
            "units_per_document": {
                "p50": _percentile(per_document, 0.50),
                "p95": _percentile(per_document, 0.95),
                "max": max(per_document, default=0),
            },
            "gold_units_per_source_instance": {
                "p50": _percentile(gold_per_document, 0.50),
                "p95": _percentile(gold_per_document, 0.95),
                "max": max(gold_per_document, default=0),
            },
            "total_unit_characters": bucket["total_unit_characters"],
            "character_expansion_vs_normalized": round(
                bucket["total_unit_characters"] / normalized_characters, 6
            ),
        }
    return {
        "dataset_identity": audit.dataset_identity,
        "parser_identity": parser_recipe.identity,
        "candidates": results,
        "warning": "Structural profile only; no candidate is the final build recipe until dev/held-out retrieval evidence is frozen.",
    }
