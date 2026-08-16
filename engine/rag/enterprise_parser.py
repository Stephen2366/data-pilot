"""EnterpriseRAG-Bench 三来源文本解析与结构质量 profiling。

官方 TXT 导出器只保证“首行标题，随后拼接 content fields”。上游字段有时已经把
换行保存为字面量 ``\\n``，所以本模块只恢复结构性换行；它刻意不使用
``unicode_escape``，避免顺手改坏 JSON、Windows 路径或代码中的其他反斜杠。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

from engine.rag.enterprise_dataset import (
    DatasetAudit,
    EnterpriseDatasetError,
    SourceInstance,
    canonical_identity,
)


@dataclass(frozen=True)
class SourceParserPolicy:
    """单一 source type 的显式解析策略。"""

    source_type: str
    decode_literal_newlines: bool = True


@dataclass(frozen=True)
class ParserRecipe:
    """normalization 行为身份；chunk recipe 不属于这一层。"""

    recipe_version: str
    source_policies: Mapping[str, SourceParserPolicy]

    @property
    def identity(self) -> str:
        return canonical_identity(
            {
                "recipe_version": self.recipe_version,
                "source_policies": {
                    key: {
                        "source_type": value.source_type,
                        "decode_literal_newlines": value.decode_literal_newlines,
                    }
                    for key, value in sorted(self.source_policies.items())
                },
            }
        )


DEFAULT_PARSER_RECIPE = ParserRecipe(
    recipe_version="enterprise-text-parser-candidate-v1",
    source_policies={
        source_type: SourceParserPolicy(source_type=source_type)
        for source_type in ("confluence", "google_drive", "jira")
    },
)


@dataclass(frozen=True)
class NormalizationEvents:
    """每次有损/结构修复都计数，禁止 silent cleanup。"""

    bom_removed: int
    actual_crlf_normalized: int
    actual_cr_normalized: int
    literal_crlf_decoded: int
    literal_lf_decoded: int
    literal_cr_decoded: int

    @property
    def literal_newlines_decoded(self) -> int:
        return self.literal_crlf_decoded + self.literal_lf_decoded + self.literal_cr_decoded


@dataclass(frozen=True)
class NormalizedDocument:
    """可回到物理原件的规范化全文；还不是 retrieval unit。"""

    source_instance: SourceInstance
    parser_identity: str
    title: str
    content: str
    content_sha256: str
    document_revision: str
    events: NormalizationEvents


def _decode_structural_newlines(text: str) -> tuple[str, int, int, int]:
    """按最长 token 优先恢复字面量换行，并返回三类替换次数。"""

    literal_crlf = text.count(r"\r\n")
    text = text.replace(r"\r\n", "\n")
    literal_lf = text.count(r"\n")
    text = text.replace(r"\n", "\n")
    literal_cr = text.count(r"\r")
    text = text.replace(r"\r", "\n")
    return text, literal_crlf, literal_lf, literal_cr


def parse_source_document(
    dataset_root: Path,
    source_instance: SourceInstance,
    recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
) -> NormalizedDocument:
    """解析一份 source instance，保持 raw identity 与 normalized revision 分离。"""

    policy = recipe.source_policies.get(source_instance.source_type)
    if policy is None or policy.source_type != source_instance.source_type:
        raise EnterpriseDatasetError(
            "parser_policy_missing", source_instance.source_type
        )
    path = dataset_root / "extracted" / Path(source_instance.relative_path)
    raw_bytes = path.read_bytes()
    if sha256(raw_bytes).hexdigest() != source_instance.content_sha256:
        raise EnterpriseDatasetError("source_changed_after_audit", str(path))
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnterpriseDatasetError("invalid_document_encoding", str(path)) from exc

    bom_removed = int(raw.startswith("\ufeff"))
    if bom_removed:
        raw = raw.removeprefix("\ufeff")
    actual_crlf = raw.count("\r\n")
    without_crlf = raw.replace("\r\n", "\n")
    actual_cr = without_crlf.count("\r")
    normalized = without_crlf.replace("\r", "\n")

    # ★ 标题由官方 export contract 的首行提供。只解正文转义，避免标题中的
    # 合法反斜杠被误当结构控制字符。
    title, separator, body = normalized.partition("\n")
    # 只用 strip 判断空值，不改写真实标题；任何 normalization 都必须有事件记录。
    if not separator or not title.strip():
        raise EnterpriseDatasetError("document_title_missing", str(path))
    literal_crlf = literal_lf = literal_cr = 0
    if policy.decode_literal_newlines:
        body, literal_crlf, literal_lf, literal_cr = _decode_structural_newlines(body)
    content = f"{title}\n{body}"
    if not body.strip():
        raise EnterpriseDatasetError("document_body_missing", str(path))
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    revision = canonical_identity(
        {
            "physical_identity": source_instance.physical_identity,
            "parser_identity": recipe.identity,
            "normalized_content_sha256": content_hash,
        }
    )
    return NormalizedDocument(
        source_instance=source_instance,
        parser_identity=recipe.identity,
        title=title,
        content=content,
        content_sha256=content_hash,
        document_revision=revision,
        events=NormalizationEvents(
            bom_removed=bom_removed,
            actual_crlf_normalized=actual_crlf,
            actual_cr_normalized=actual_cr,
            literal_crlf_decoded=literal_crlf,
            literal_lf_decoded=literal_lf,
            literal_cr_decoded=literal_cr,
        ),
    )


def iter_normalized_documents(
    audit: DatasetAudit,
    recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
) -> Iterable[NormalizedDocument]:
    """流式解析完整 corpus，避免同时持有约 264 MB 原文和规范化副本。"""

    for source_instance in audit.source_instances:
        yield parse_source_document(audit.dataset_root, source_instance, recipe)


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    index = max(0, min(len(values) - 1, int((len(values) - 1) * percentile)))
    return sorted(values)[index]


def _distribution(values: list[int]) -> dict[str, int]:
    return {
        "min": min(values, default=0),
        "p50": _percentile(values, 0.50),
        "p95": _percentile(values, 0.95),
        "p99": _percentile(values, 0.99),
        "max": max(values, default=0),
    }


def profile_normalized_corpus(
    audit: DatasetAudit,
    recipe: ParserRecipe = DEFAULT_PARSER_RECIPE,
) -> dict[str, Any]:
    """对完整 corpus 生成结构摘要，不写出 normalized 大文件。"""

    by_source: dict[str, dict[str, Any]] = {}
    gold_ids = {
        document_id
        for question in audit.selected_questions
        for document_id in question.expected_document_ids
    }
    gold_lengths: list[int] = []
    total_events: Counter[str] = Counter()
    for document in iter_normalized_documents(audit, recipe):
        source_type = document.source_instance.source_type
        bucket = by_source.setdefault(
            source_type,
            {
                "document_count": 0,
                "character_lengths": [],
                "line_counts": [],
                "paragraph_counts": [],
                "documents_with_literal_newline_repairs": 0,
                "literal_newlines_decoded": 0,
            },
        )
        bucket["document_count"] += 1
        bucket["character_lengths"].append(len(document.content))
        bucket["line_counts"].append(document.content.count("\n") + 1)
        paragraphs = [part for part in document.content.split("\n\n") if part.strip()]
        bucket["paragraph_counts"].append(len(paragraphs))
        repaired = document.events.literal_newlines_decoded
        bucket["documents_with_literal_newline_repairs"] += int(repaired > 0)
        bucket["literal_newlines_decoded"] += repaired
        total_events.update(
            {
                "bom_removed": document.events.bom_removed,
                "actual_crlf_normalized": document.events.actual_crlf_normalized,
                "actual_cr_normalized": document.events.actual_cr_normalized,
                "literal_crlf_decoded": document.events.literal_crlf_decoded,
                "literal_lf_decoded": document.events.literal_lf_decoded,
                "literal_cr_decoded": document.events.literal_cr_decoded,
            }
        )
        if document.source_instance.logical_document_id in gold_ids:
            gold_lengths.append(len(document.content))

    source_summary: dict[str, Any] = {}
    for source_type, bucket in sorted(by_source.items()):
        source_summary[source_type] = {
            "document_count": bucket["document_count"],
            "character_length": _distribution(bucket["character_lengths"]),
            "line_count": _distribution(bucket["line_counts"]),
            "paragraph_count": _distribution(bucket["paragraph_counts"]),
            "documents_with_literal_newline_repairs": bucket[
                "documents_with_literal_newline_repairs"
            ],
            "literal_newlines_decoded": bucket["literal_newlines_decoded"],
        }
    return {
        "dataset_identity": audit.dataset_identity,
        "corpus_identity": audit.corpus_identity,
        "parser_recipe_version": recipe.recipe_version,
        "parser_identity": recipe.identity,
        "source_summary": source_summary,
        "gold_source_instance_character_length": _distribution(gold_lengths),
        "normalization_events": dict(sorted(total_events.items())),
    }
