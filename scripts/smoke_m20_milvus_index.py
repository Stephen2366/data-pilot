"""M20 Milvus index hygiene smoke.

用途：
- 创建一个唯一 Milvus collection；
- 写入当前 193 条 schema docs；
- 验证 clean collection 下 `row_count == len(schema_documents)`；
- 输出 schema_docs_hash、embedding provider/model/dimension 和典型 query 的召回摘要。

脚本只在显式运行时连接 Milvus / embedding 服务；默认项目路径仍是 in-memory deterministic。
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / ".agent_work" / "temp" / "m20-milvus-index-smoke.md"

from app.core.config import get_settings
from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import DEFAULT_RELATIONS_PATH, build_schema_documents, schema_documents_hash
from engine.schema_retrieval.retriever import retrieve_schema
from engine.schema_retrieval.vector_index import MilvusVectorIndex


QUESTIONS = [
    "2026 年 6 月 GMV 是多少？",
    "JUNE_FIXED_50 在哪个渠道使用最多？",
    "2026 年 6 月一级类目 GMV Top 是什么？",
    "2026 年 6 月退款率最高的商品是什么？",
    "Aurora 耳机 2026 年 6 月历史均价是多少？",
]


def _set_unique_collection(prefix: str) -> str:
    """给本次 smoke 设置唯一 collection 名，避免碰到历史污染。"""

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    collection_name = f"{prefix}_{stamp}_{uuid4().hex[:8]}"
    os.environ["MILVUS_COLLECTION"] = collection_name
    os.environ["SCHEMA_VECTOR_BACKEND"] = "milvus"
    get_settings.cache_clear()
    return collection_name


def _build_lines(collection_name: str, *, keep_collection: bool) -> tuple[list[str], int]:
    """执行 smoke 并返回 Markdown lines 与退出码。"""

    settings = get_settings()
    domain_schema = load_domain_schema()
    documents = build_schema_documents(domain_schema, relations_path=DEFAULT_RELATIONS_PATH)
    docs_hash = schema_documents_hash(documents)
    index = None
    exit_code = 0
    lines = [
        "# M20 Milvus Index Hygiene Smoke",
        "",
        f"- generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- collection_name: {collection_name}",
        f"- milvus_uri: {settings.milvus_uri}",
        f"- schema_docs_count: {len(documents)}",
        f"- schema_docs_hash: {docs_hash}",
        f"- embedding_provider: {settings.schema_embedding_provider}",
        f"- qwen_embedding_model: {settings.qwen_embedding_model}",
        f"- qwen_embedding_dimensions: {settings.qwen_embedding_dimensions}",
        f"- siliconflow_embedding_model: {settings.siliconflow_embedding_model}",
        f"- siliconflow_embedding_dimensions: {settings.siliconflow_embedding_dimensions}",
        "",
    ]
    try:
        from engine.schema_retrieval.retriever import _build_embedding_provider, _configured_milvus_dimension

        index = MilvusVectorIndex(
            documents=documents,
            embedding_provider=_build_embedding_provider(settings),
            collection_name=collection_name,
            uri=settings.milvus_uri,
            dimension=_configured_milvus_dimension(settings),
            reset_collection=True,
        )
        row_count = index.final_row_count
        status = "PASS" if row_count == len(documents) else "FAIL"
        if status != "PASS":
            exit_code = 1
        lines.extend(
            [
                "## Collection Check",
                "",
                f"- status: {status}",
                f"- initial_row_count: {index.initial_row_count}",
                f"- inserted_document_count: {index.inserted_document_count}",
                f"- final_row_count: {row_count}",
                f"- expected_row_count: {len(documents)}",
                "",
                "## Retrieval Samples",
                "",
                "| question | keyword_hits | vector_hits | merged_hits | top_docs |",
                "|---|---:|---:|---:|---|",
            ]
        )
        for question in QUESTIONS:
            result = retrieve_schema(
                question=question,
                user_role="ops",
                top_k=10,
                domain_schema=domain_schema,
                relations_path=DEFAULT_RELATIONS_PATH,
                vector_index=index,
            )
            top_docs = ", ".join(hit.document.doc_id for hit in result.merged_hits[:5])
            lines.append(
                f"| {question} | {len(result.keyword_hits)} | {len(result.vector_hits)} | {len(result.merged_hits)} | {top_docs} |"
            )
    except Exception as exc:  # noqa: BLE001 - smoke 需要把真实失败写进报告。
        exit_code = 1
        lines.extend(["## Collection Check", "", "- status: FAIL", f"- error: {exc}", ""])
    finally:
        if index is not None:
            if keep_collection:
                lines.extend(["", "## Cleanup", "", "- kept_collection: yes"])
            else:
                index.drop_collection()
                lines.extend(["", "## Cleanup", "", "- kept_collection: no", "- dropped_collection: yes"])
            index.close()
    return lines, exit_code


def main() -> int:
    """CLI 入口。"""

    parser = argparse.ArgumentParser(description="Run M20 Milvus index hygiene smoke.")
    parser.add_argument("--collection-prefix", default="datapilot_schema_docs_m20")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--keep-collection", action="store_true")
    args = parser.parse_args()

    collection_name = _set_unique_collection(args.collection_prefix)
    lines, exit_code = _build_lines(collection_name, keep_collection=args.keep_collection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"smoke_report={args.output}")
    print(f"collection_name={collection_name}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
