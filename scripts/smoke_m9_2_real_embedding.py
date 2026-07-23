"""M9.2 真实中文 embedding + Milvus 对比 smoke。

脚本会调用 SiliconFlow embeddings API，因此只在显式运行时使用；默认 pytest 不联网、不消耗额度。
输出报告写入 `.agent_work/temp/m9_2-real-embedding-smoke.md`。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.run_eval import EvalCase, load_cases
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents
from engine.schema_retrieval.embedding_provider import (
    DEFAULT_SILICONFLOW_BASE_URL,
    DEFAULT_SILICONFLOW_EMBEDDING_MODEL,
    SiliconFlowEmbeddingProvider,
)
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import retrieve_schema
from engine.schema_retrieval.vector_index import (
    DEFAULT_MILVUS_URI,
    DeterministicEmbeddingProvider,
    MilvusVectorIndex,
    VectorIndex,
)

RELATIONS_PATH = PROJECT_ROOT / "domain_pack" / "schema_desc" / "relations.yaml"
REPORT_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m9_2-real-embedding-smoke.md"


def _schema_join_cases() -> dict[str, list[EvalCase]]:
    """准备 M9/M9.1/M9.2 对比用例分组。"""

    formal = [
        case
        for case in load_cases(PROJECT_ROOT / "eval" / "cases" / "phase3a-regression.yaml")
        if case.security_expectation == "allow"
    ]
    challenge = [
        case
        for case in load_cases(PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml")
        if {"schema_retrieval", "join_path"} & set(case.phase3a_capabilities)
    ]
    diagnostic = [
        case
        for case in load_cases(
            PROJECT_ROOT / "eval" / "cases" / "database-upgrade-challenge.yaml",
            extra_cases=[PROJECT_ROOT / "eval" / "cases" / "phase3a-diagnostic-benchmark.yaml"],
        )
        if {"schema_retrieval", "join_path"} & set(case.phase3a_capabilities)
    ]
    return {
        "formal_allow": formal,
        "challenge_schema_join": challenge,
        "diagnostic_schema_join": diagnostic,
    }


def _score_cases(
    cases: list[EvalCase],
    *,
    vector_index: VectorIndex | None,
    top_k: int,
    hit_mode: str = "merged",
) -> dict[str, object]:
    """统计表、字段/指标和 JoinPath 命中。"""

    domain_schema = load_domain_schema()
    table_expected = table_hit = item_expected = item_hit = join_cases = join_hit = 0
    misses: list[str] = []

    for case in cases:
        result = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=top_k,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
            vector_index=vector_index,
        )
        hits = result.vector_hits if hit_mode == "vector_only" else result.merged_hits
        graph = build_schema_graph(hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
        expected_items = set(case.expected_columns) | set(case.expected_metrics)
        actual_items = set(graph.field_names) | set(graph.metrics)
        missing_tables = sorted(set(case.expected_tables) - set(graph.tables))
        missing_items = sorted(expected_items - actual_items)

        table_expected += len(case.expected_tables)
        table_hit += len(set(case.expected_tables) & set(graph.tables))
        item_expected += len(expected_items)
        item_hit += len(expected_items & actual_items)
        if "join_path" in case.phase3a_capabilities or case.task_type == "multi_table":
            join_cases += 1
            if graph.join_paths:
                join_hit += 1
        if missing_tables or missing_items:
            misses.append(f"{case.case_id}: missing_tables={missing_tables}, missing_items={missing_items}")

    return {
        "cases": len(cases),
        "top_k": top_k,
        "hit_mode": hit_mode,
        "table_recall": f"{table_hit}/{table_expected}",
        "item_recall": f"{item_hit}/{item_expected}",
        "join_path": f"{join_hit}/{join_cases}",
        "misses": misses,
    }


def _format_result(label: str, result: dict[str, object]) -> list[str]:
    """把一组统计结果转成 Markdown 行。"""

    lines = [
        f"### {label}",
        "",
        f"- cases: {result['cases']}",
        f"- table_recall: {result['table_recall']}",
        f"- item_recall: {result['item_recall']}",
        f"- join_path: {result['join_path']}",
        "- misses:",
    ]
    misses = list(result["misses"])
    if misses:
        lines.extend(f"  - {item}" for item in misses)
    else:
        lines.append("  - none")
    lines.append("")
    return lines


def main() -> int:
    """执行真实 embedding + Milvus 对比。"""

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("SILICONFLOW_API_KEY", "")
    if not api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is required for M9.2 smoke.")
    base_url = os.getenv("SILICONFLOW_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL
    milvus_uri = os.getenv("MILVUS_URI") or DEFAULT_MILVUS_URI
    model = os.getenv("SILICONFLOW_EMBEDDING_MODEL") or DEFAULT_SILICONFLOW_EMBEDDING_MODEL
    dimensions = os.getenv("SILICONFLOW_EMBEDDING_DIMENSIONS")
    parsed_dimensions = int(dimensions) if dimensions else None

    domain_schema = load_domain_schema()
    documents = build_schema_documents(domain_schema, relations_path=RELATIONS_PATH)
    fake_collection = f"datapilot_m9_2_fake_{uuid4().hex[:8]}"
    real_collection = f"datapilot_m9_2_real_{uuid4().hex[:8]}"
    fake_index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name=fake_collection,
        uri=milvus_uri,
        reset_collection=True,
    )
    real_index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=SiliconFlowEmbeddingProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            dimensions=parsed_dimensions,
            timeout=60.0,
        ),
        collection_name=real_collection,
        uri=milvus_uri,
        reset_collection=True,
    )

    try:
        lines = [
            "# M9.2 Real Embedding Smoke",
            "",
            f"- milvus_uri: {milvus_uri}",
            f"- siliconflow_base_url: {base_url}",
            f"- embedding_model: {model}",
            f"- embedding_dimensions: {parsed_dimensions or 'model_default'}",
            f"- fake_collection: {fake_collection}",
            f"- real_collection: {real_collection}",
            "",
        ]
        for group_name, cases in _schema_join_cases().items():
            lines.extend(
                _format_result(
                    f"{group_name} / in_memory_fake / merged_top30",
                    _score_cases(cases, vector_index=None, top_k=30),
                )
            )
            lines.extend(
                _format_result(
                    f"{group_name} / milvus_fake / merged_top30",
                    _score_cases(cases, vector_index=fake_index, top_k=30),
                )
            )
            lines.extend(
                _format_result(
                    f"{group_name} / milvus_siliconflow / merged_top30",
                    _score_cases(cases, vector_index=real_index, top_k=30),
                )
            )
            lines.extend(
                _format_result(
                    f"{group_name} / in_memory_fake / vector_only_top12",
                    _score_cases(cases, vector_index=None, top_k=12, hit_mode="vector_only"),
                )
            )
            lines.extend(
                _format_result(
                    f"{group_name} / milvus_siliconflow / vector_only_top12",
                    _score_cases(cases, vector_index=real_index, top_k=12, hit_mode="vector_only"),
                )
            )
    finally:
        fake_index.drop_collection()
        real_index.drop_collection()
        fake_index.close()
        real_index.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
