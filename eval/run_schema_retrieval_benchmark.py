"""Schema Retrieval only benchmark.

这个 runner 专门评估 Schema Retrieval / embedding 能不能召回正确上下文，不调用 LLM，
也不执行 SQL。它用于回答“Milvus + embedding 是否让 schema 召回变好”，避免完整
Text2SQL diagnostic 被模型生成波动淹没。
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import (
    DEFAULT_RELATIONS_PATH,
    build_schema_documents,
    schema_documents_hash,
)
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import build_configured_schema_vector_index, retrieve_schema
from engine.schema_retrieval.vector_index import VectorIndex

DEFAULT_CASES = PROJECT_ROOT / "eval" / "cases" / "schema-retrieval-embedding-benchmark.yaml"
DEFAULT_REPORT = PROJECT_ROOT / ".agent_work" / "temp" / "schema-retrieval-embedding-report.md"


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    """retrieval-only case：只描述期望召回的表、字段、指标和 relation。"""

    case_id: str
    question: str
    category: str
    user_role: str = "ops"
    expected_tables: list[str] = field(default_factory=list)
    expected_columns: list[str] = field(default_factory=list)
    expected_metrics: list[str] = field(default_factory=list)
    expected_relations: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    """单条 retrieval benchmark 的评分结果。"""

    case: RetrievalBenchmarkCase
    keyword_overall_recall: float
    vector_overall_recall: float
    table_recall: float
    column_recall: float
    metric_recall: float
    relation_recall: float
    overall_recall: float
    missing_tables: list[str]
    missing_columns: list[str]
    missing_metrics: list[str]
    missing_relations: list[str]
    keyword_top_docs: list[str]
    vector_top_docs: list[str]
    merged_top_docs: list[str]


def load_benchmark_cases(path: Path = DEFAULT_CASES) -> list[RetrievalBenchmarkCase]:
    """加载 retrieval-only YAML 用例。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[RetrievalBenchmarkCase] = []
    seen_ids: set[str] = set()
    for item in payload.get("cases") or []:
        case_id = str(item["id"])
        if case_id in seen_ids:
            raise ValueError(f"duplicate retrieval benchmark case id: {case_id}")
        seen_ids.add(case_id)
        cases.append(
            RetrievalBenchmarkCase(
                case_id=case_id,
                question=str(item["question"]),
                category=str(item.get("category", "general")),
                user_role=str(item.get("user_role", "ops")),
                expected_tables=list(item.get("expected_tables") or []),
                expected_columns=list(item.get("expected_columns") or []),
                expected_metrics=list(item.get("expected_metrics") or []),
                expected_relations=list(item.get("expected_relations") or []),
                notes=str(item.get("notes", "")),
            )
        )
    return cases


def _recall(expected: list[str], actual: set[str]) -> tuple[float, list[str]]:
    """计算一类期望项的召回率。"""

    if not expected:
        return 1.0, []
    missing = sorted(item for item in expected if item not in actual)
    return (len(expected) - len(missing)) / len(expected), missing


def _overall_recall(*values: float) -> float:
    """简单平均四类 recall，避免单类字段很多时吞掉 relation / metric 信号。"""

    return sum(values) / len(values)


def _graph_recall(
    case: RetrievalBenchmarkCase,
    *,
    tables: set[str],
    columns: set[str],
    metrics: set[str],
    relations: set[str],
) -> tuple[float, list[str], list[str], list[str], list[str]]:
    """对一组 graph 结果计算四类 recall。

    这个 helper 让报告能同时展示 keyword / vector / merged 三条链路。M20 后要评估
    embedding 价值，不能只看 merged；如果 vector 变好但 merged 没变，问题就在融合策略。
    """

    table_recall, missing_tables = _recall(case.expected_tables, tables)
    column_recall, missing_columns = _recall(case.expected_columns, columns)
    metric_recall, missing_metrics = _recall(case.expected_metrics, metrics)
    relation_recall, missing_relations = _recall(case.expected_relations, relations)
    return (
        _overall_recall(table_recall, column_recall, metric_recall, relation_recall),
        missing_tables,
        missing_columns,
        missing_metrics,
        missing_relations,
    )


def run_benchmark(
    cases: list[RetrievalBenchmarkCase],
    *,
    top_k: int,
    schema_retrieval_profile: str = "default",
    vector_index: VectorIndex | None = None,
    fusion_strategy: str = "weighted",
) -> list[RetrievalBenchmarkResult]:
    """执行 retrieval-only benchmark，并把候选 fusion 显式传给 retriever。"""

    domain_schema = load_domain_schema()
    results: list[RetrievalBenchmarkResult] = []
    for case in cases:
        retrieval = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=top_k,
            domain_schema=domain_schema,
            relations_path=DEFAULT_RELATIONS_PATH,
            vector_index=vector_index,
            schema_retrieval_profile=schema_retrieval_profile,
            fusion_strategy=fusion_strategy,
        )
        keyword_graph = build_schema_graph(
            retrieval.keyword_hits,
            domain_schema=domain_schema,
            relations_path=DEFAULT_RELATIONS_PATH,
        )
        vector_graph = build_schema_graph(
            retrieval.vector_hits,
            domain_schema=domain_schema,
            relations_path=DEFAULT_RELATIONS_PATH,
        )
        merged_graph = build_schema_graph(
            retrieval.merged_hits,
            domain_schema=domain_schema,
            relations_path=DEFAULT_RELATIONS_PATH,
        )
        keyword_overall, *_keyword_missing = _graph_recall(
            case,
            tables=set(keyword_graph.tables),
            columns=set(keyword_graph.field_names),
            metrics=set(keyword_graph.metrics),
            relations={relation["id"] for relation in keyword_graph.relations},
        )
        vector_overall, *_vector_missing = _graph_recall(
            case,
            tables=set(vector_graph.tables),
            columns=set(vector_graph.field_names),
            metrics=set(vector_graph.metrics),
            relations={relation["id"] for relation in vector_graph.relations},
        )
        actual_tables = set(merged_graph.tables)
        actual_columns = set(merged_graph.field_names)
        actual_metrics = set(merged_graph.metrics)
        actual_relations = {relation["id"] for relation in merged_graph.relations}
        merged_overall, missing_tables, missing_columns, missing_metrics, missing_relations = _graph_recall(
            case,
            tables=actual_tables,
            columns=actual_columns,
            metrics=actual_metrics,
            relations=actual_relations,
        )
        table_recall, _ = _recall(case.expected_tables, actual_tables)
        column_recall, _ = _recall(case.expected_columns, actual_columns)
        metric_recall, _ = _recall(case.expected_metrics, actual_metrics)
        relation_recall, _ = _recall(case.expected_relations, actual_relations)
        results.append(
            RetrievalBenchmarkResult(
                case=case,
                keyword_overall_recall=keyword_overall,
                vector_overall_recall=vector_overall,
                table_recall=table_recall,
                column_recall=column_recall,
                metric_recall=metric_recall,
                relation_recall=relation_recall,
                overall_recall=merged_overall,
                missing_tables=missing_tables,
                missing_columns=missing_columns,
                missing_metrics=missing_metrics,
                missing_relations=missing_relations,
                keyword_top_docs=[hit.document.doc_id for hit in retrieval.keyword_hits[:5]],
                vector_top_docs=[hit.document.doc_id for hit in retrieval.vector_hits[:5]],
                merged_top_docs=[hit.document.doc_id for hit in retrieval.merged_hits[:8]],
            )
        )
    return results


def _average(values: list[float]) -> float:
    """安全平均值。"""

    return sum(values) / len(values) if values else 0.0


def write_report(
    results: list[RetrievalBenchmarkResult],
    *,
    path: Path,
    metadata: dict[str, Any],
) -> None:
    """写 Markdown 报告。"""

    category_names = sorted({result.case.category for result in results})
    lines = [
        "# Schema Retrieval Embedding Benchmark",
        "",
        f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- total_cases: {len(results)}",
        f"- avg_overall_recall: {_average([result.overall_recall for result in results]):.3f}",
        f"- avg_keyword_overall_recall: {_average([result.keyword_overall_recall for result in results]):.3f}",
        f"- avg_vector_overall_recall: {_average([result.vector_overall_recall for result in results]):.3f}",
        f"- avg_table_recall: {_average([result.table_recall for result in results]):.3f}",
        f"- avg_column_recall: {_average([result.column_recall for result in results]):.3f}",
        f"- avg_metric_recall: {_average([result.metric_recall for result in results]):.3f}",
        f"- avg_relation_recall: {_average([result.relation_recall for result in results]):.3f}",
        "",
        "## Runtime Metadata",
        "",
        "| key | value |",
        "|---|---|",
    ]
    for key, value in sorted(metadata.items()):
        lines.append(f"| {key} | {value} |")

    lines.extend(["", "## Category Summary", "", "| category | count | avg_overall | avg_table | avg_column | avg_metric | avg_relation |", "|---|---:|---:|---:|---:|---:|---:|"])
    for category in category_names:
        group = [result for result in results if result.case.category == category]
        lines.append(
            "| {category} | {count} | {overall:.3f} | {table:.3f} | {column:.3f} | {metric:.3f} | {relation:.3f} |".format(
                category=category,
                count=len(group),
                overall=_average([result.overall_recall for result in group]),
                table=_average([result.table_recall for result in group]),
                column=_average([result.column_recall for result in group]),
                metric=_average([result.metric_recall for result in group]),
                relation=_average([result.relation_recall for result in group]),
            )
        )

    lines.extend(
        [
            "",
            "## Case Summary",
            "",
            "| case_id | category | keyword_overall | vector_overall | merged_overall | table | column | metric | relation | missing |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for result in results:
        missing_parts = []
        if result.missing_tables:
            missing_parts.append("tables=" + ",".join(result.missing_tables))
        if result.missing_columns:
            missing_parts.append("columns=" + ",".join(result.missing_columns))
        if result.missing_metrics:
            missing_parts.append("metrics=" + ",".join(result.missing_metrics))
        if result.missing_relations:
            missing_parts.append("relations=" + ",".join(result.missing_relations))
        lines.append(
            "| {case_id} | {category} | {keyword:.3f} | {vector:.3f} | {overall:.3f} | {table:.3f} | {column:.3f} | {metric:.3f} | {relation:.3f} | {missing} |".format(
                case_id=result.case.case_id,
                category=result.case.category,
                keyword=result.keyword_overall_recall,
                vector=result.vector_overall_recall,
                overall=result.overall_recall,
                table=result.table_recall,
                column=result.column_recall,
                metric=result.metric_recall,
                relation=result.relation_recall,
                missing="; ".join(missing_parts) or "-",
            )
        )

    lines.extend(["", "## Top Docs", "", "| case_id | keyword_top_docs | vector_top_docs | merged_top_docs |", "|---|---|---|---|"])
    for result in results:
        lines.append(
            f"| {result.case.case_id} | {', '.join(result.keyword_top_docs) or '-'} | {', '.join(result.vector_top_docs) or '-'} | {', '.join(result.merged_top_docs) or '-'} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _maybe_unique_collection(prefix: str) -> str | None:
    """Milvus benchmark 默认给当前进程设置唯一 collection，避免污染旧实验。"""

    settings = get_settings()
    if settings.schema_vector_backend.lower() != "milvus":
        return None
    if os.environ.get("MILVUS_COLLECTION"):
        return settings.milvus_collection
    collection = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    os.environ["MILVUS_COLLECTION"] = collection
    get_settings.cache_clear()
    return collection


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""

    parser = argparse.ArgumentParser(description="Run schema retrieval only benchmark.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--schema-retrieval-profile", default="default")
    parser.add_argument(
        "--fusion-strategy",
        choices=["weighted", "rrf"],
        default="weighted",
        help="M21 显式 fusion 实验；默认 weighted 保持现有检索行为。",
    )
    parser.add_argument("--collection-prefix", default="datapilot_schema_retrieval_bench")
    args = parser.parse_args(argv)

    collection_name = _maybe_unique_collection(args.collection_prefix)
    settings = get_settings()
    cases = load_benchmark_cases(args.cases)
    vector_index: VectorIndex | None = None
    # ★ 两组 benchmark 都写同一版 schema docs 元数据；否则 deterministic 基线缺少 hash，
    # 无法证明它和 Milvus 候选使用的是同一份检索语料。
    domain_schema = load_domain_schema()
    benchmark_documents = build_schema_documents(domain_schema, relations_path=DEFAULT_RELATIONS_PATH)
    documents_count = len(benchmark_documents)
    docs_hash = schema_documents_hash(benchmark_documents)
    try:
        if settings.schema_vector_backend.lower() == "milvus":
            vector_index, documents, docs_hash = build_configured_schema_vector_index(
                domain_schema=domain_schema,
                schema_retrieval_profile=args.schema_retrieval_profile,
            )
            documents_count = len(documents)
        results = run_benchmark(
            cases,
            top_k=args.top_k,
            schema_retrieval_profile=args.schema_retrieval_profile,
            vector_index=vector_index,
            fusion_strategy=args.fusion_strategy,
        )
        metadata = {
            "schema_vector_backend": settings.schema_vector_backend,
            "schema_embedding_provider": settings.schema_embedding_provider,
            "schema_retrieval_profile": args.schema_retrieval_profile,
            "fusion_strategy": args.fusion_strategy,
            "top_k": args.top_k,
            "milvus_collection": collection_name or settings.milvus_collection,
            "milvus_dimension": getattr(vector_index, "dimension", None),
            "milvus_final_row_count": getattr(vector_index, "final_row_count", None),
            "schema_docs_count": documents_count,
            "schema_docs_hash": docs_hash,
            "qwen_embedding_model": settings.qwen_embedding_model,
            "qwen_embedding_dimensions": settings.qwen_embedding_dimensions,
        }
        write_report(results, path=args.report, metadata=metadata)
        print(f"report={args.report}")
        print(f"avg_overall_recall={_average([result.overall_recall for result in results]):.3f}")
        print(f"avg_keyword_overall_recall={_average([result.keyword_overall_recall for result in results]):.3f}")
        print(f"avg_vector_overall_recall={_average([result.vector_overall_recall for result in results]):.3f}")
        print(f"avg_table_recall={_average([result.table_recall for result in results]):.3f}")
        print(f"avg_column_recall={_average([result.column_recall for result in results]):.3f}")
        print(f"avg_metric_recall={_average([result.metric_recall for result in results]):.3f}")
        print(f"avg_relation_recall={_average([result.relation_recall for result in results]):.3f}")
        if collection_name:
            print(f"milvus_collection={collection_name}")
            print(f"milvus_final_row_count={getattr(vector_index, 'final_row_count', None)}")
        return 0
    finally:
        close_index = getattr(vector_index, "close", None)
        if callable(close_index):
            close_index()


if __name__ == "__main__":
    raise SystemExit(main())
