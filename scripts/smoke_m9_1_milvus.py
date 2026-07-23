"""M9.1 Milvus adapter 实验 smoke。

运行后会用同一批 Schema 文档分别走默认 in-memory index 和 Milvus index，输出召回统计到
`.agent_work/temp/m9_1-milvus-smoke.md`。它是实验脚本，不作为主线 pytest 默认依赖。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.run_eval import EvalCase, load_cases
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import retrieve_schema
from engine.schema_retrieval.vector_index import DeterministicEmbeddingProvider, MilvusVectorIndex, VectorIndex

RELATIONS_PATH = PROJECT_ROOT / "domain_pack" / "schema_desc" / "relations.yaml"
REPORT_PATH = PROJECT_ROOT / ".agent_work" / "temp" / "m9_1-milvus-smoke.md"
MILVUS_URI = "http://127.0.0.1:19530"


def _schema_join_cases() -> dict[str, list[EvalCase]]:
    """准备 M9/M9.1 对比用例分组。"""

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
) -> dict[str, object]:
    """统计表、字段/指标和 JoinPath 命中。"""

    domain_schema = load_domain_schema()
    table_expected = table_hit = item_expected = item_hit = join_cases = join_hit = 0
    misses: list[str] = []

    for case in cases:
        result = retrieve_schema(
            question=case.question,
            user_role=case.user_role,
            top_k=30,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
            vector_index=vector_index,
        )
        graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
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
    """执行 in-memory vs Milvus 的 M9.1 对比 smoke。"""

    domain_schema = load_domain_schema()
    documents = build_schema_documents(domain_schema, relations_path=RELATIONS_PATH)
    collection_name = f"datapilot_m9_1_smoke_{uuid4().hex[:8]}"
    milvus_index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name=collection_name,
        uri=MILVUS_URI,
        reset_collection=True,
    )

    try:
        lines = [
            "# M9.1 Milvus Smoke",
            "",
            f"- collection_name: {collection_name}",
            f"- milvus_uri: {MILVUS_URI}",
            "",
        ]
        for group_name, cases in _schema_join_cases().items():
            lines.extend(_format_result(f"{group_name} / in_memory", _score_cases(cases, vector_index=None)))
            lines.extend(_format_result(f"{group_name} / milvus", _score_cases(cases, vector_index=milvus_index)))
    finally:
        milvus_index.drop_collection()
        milvus_index.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"report={REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
