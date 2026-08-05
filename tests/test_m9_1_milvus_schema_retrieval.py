"""M9.1 Milvus adapter 实验测试。

这些测试只在本机 Milvus 可用时跑真实服务；默认 M9 pytest 仍不依赖外部向量库。这样既能验证
方案 B 的效果，又不会把主线自动化绑死在 Docker 环境上。
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents, schema_documents_hash
from engine.schema_retrieval.graph import build_schema_graph
from engine.schema_retrieval.retriever import retrieve_schema
from engine.schema_retrieval.vector_index import DeterministicEmbeddingProvider, MilvusVectorIndex


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELATIONS_PATH = PROJECT_ROOT / "domain_pack" / "schema_desc" / "relations.yaml"
MILVUS_URI = "http://127.0.0.1:19530"


def _milvus_available() -> bool:
    """轻量探测本机 Milvus；不可用时跳过实验测试。"""

    try:
        from pymilvus import MilvusClient

        client = MilvusClient(uri=MILVUS_URI)
        client.list_collections()
        client.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _milvus_available(), reason="Milvus is not available on 127.0.0.1:19530")


def test_milvus_vector_index_searches_schema_documents() -> None:
    """Milvus adapter 要复用 M9 的 SchemaHit 契约，并返回 source=milvus。"""

    domain_schema = load_domain_schema()
    documents = build_schema_documents(domain_schema, relations_path=RELATIONS_PATH)
    collection_name = f"datapilot_m9_1_test_{uuid4().hex[:8]}"
    index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name=collection_name,
        uri=MILVUS_URI,
        reset_collection=True,
    )

    try:
        hits = index.search("JUNE_FIXED_50 在哪个渠道使用最多？", top_k=12)
    finally:
        index.drop_collection()

    assert hits
    assert {hit.source for hit in hits} == {"milvus"}
    assert all(hit.rank >= 1 for hit in hits)
    assert any(hit.doc_type == "relation_doc" for hit in hits)


def test_retrieve_schema_can_use_explicit_milvus_index_without_changing_default() -> None:
    """显式注入 Milvus index 时走方案 B；未注入时默认 M9 in-memory 行为保持不变。"""

    domain_schema = load_domain_schema()
    documents = build_schema_documents(domain_schema, relations_path=RELATIONS_PATH)
    collection_name = f"datapilot_m9_1_retriever_{uuid4().hex[:8]}"
    milvus_index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name=collection_name,
        uri=MILVUS_URI,
        reset_collection=True,
    )

    try:
        result = retrieve_schema(
            question="2026 年 6 月各渠道 GMV 排名",
            user_role="ops",
            top_k=24,
            domain_schema=domain_schema,
            relations_path=RELATIONS_PATH,
            vector_index=milvus_index,
        )
        graph = build_schema_graph(result.merged_hits, domain_schema=domain_schema, relations_path=RELATIONS_PATH)
    finally:
        milvus_index.drop_collection()

    assert result.vector_hits
    assert {hit.source for hit in result.vector_hits} == {"milvus"}
    assert {"orders", "channels"} <= set(graph.tables)
    assert graph.join_paths


def test_milvus_reuse_requires_and_reads_schema_docs_hash() -> None:
    """M23：真实 Milvus 必须能读回 collection 的内容版本标记后才允许复用。"""

    documents = build_schema_documents(load_domain_schema(), relations_path=RELATIONS_PATH)
    collection_name = f"datapilot_m23_hash_reuse_{uuid4().hex[:8]}"
    first_index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name=collection_name,
        uri=MILVUS_URI,
        reset_collection=True,
    )

    try:
        reused_index = MilvusVectorIndex(
            documents=documents,
            embedding_provider=DeterministicEmbeddingProvider(),
            collection_name=collection_name,
            uri=MILVUS_URI,
        )
    finally:
        first_index.drop_collection()

    assert reused_index.schema_docs_hash == schema_documents_hash(documents)
    assert reused_index.initial_row_count == len(documents)
    assert reused_index.inserted_document_count == 0
