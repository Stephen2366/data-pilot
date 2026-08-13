"""M20 Schema Retrieval / Milvus index hygiene tests."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from engine.nl2sql.schema_loader import load_domain_schema
from engine.schema_retrieval.document_builder import build_schema_documents, schema_documents_hash
from engine.schema_retrieval.retriever import build_configured_schema_vector_index
from engine.schema_retrieval.vector_index import DeterministicEmbeddingProvider, MilvusVectorIndex


def test_schema_documents_hash_is_stable_for_same_documents() -> None:
    """schema docs hash 是 M20 实验版本标记，同一批文档必须稳定。"""

    documents = build_schema_documents(load_domain_schema())

    assert schema_documents_hash(documents) == schema_documents_hash(list(reversed(documents)))
    assert len(schema_documents_hash(documents)) == 64


def test_milvus_index_skips_insert_when_existing_collection_hash_is_clean(monkeypatch) -> None:
    """已有 collection 只有内容 hash 也一致时，才能复用且不重复 insert。"""

    documents = build_schema_documents(load_domain_schema())[:2]
    fake_module = _install_fake_pymilvus(
        monkeypatch,
        row_count=len(documents),
        schema_docs_hash=schema_documents_hash(documents),
    )

    index = MilvusVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
        collection_name="clean_collection",
    )

    assert fake_module.MilvusClient.insert_calls == 0
    assert index.initial_row_count == len(documents)
    assert index.inserted_document_count == 0


def test_milvus_index_refuses_same_count_but_stale_schema_docs(monkeypatch) -> None:
    """M23：不能只因行数相同，就把旧业务语义向量误映射为当前文档。"""

    documents = build_schema_documents(load_domain_schema())[:2]
    _install_fake_pymilvus(
        monkeypatch,
        row_count=len(documents),
        schema_docs_hash="stale-schema-docs-hash",
    )

    with pytest.raises(RuntimeError, match="content hash does not match"):
        MilvusVectorIndex(
            documents=documents,
            embedding_provider=DeterministicEmbeddingProvider(),
            collection_name="stale_same_count_collection",
        )


def test_milvus_index_refuses_polluted_existing_collection(monkeypatch) -> None:
    """已有 collection 行数与 schema docs 不一致时直接失败，避免继续污染实验。"""

    documents = build_schema_documents(load_domain_schema())[:2]
    _install_fake_pymilvus(monkeypatch, row_count=99, schema_docs_hash=None)

    with pytest.raises(RuntimeError, match="not clean"):
        MilvusVectorIndex(
            documents=documents,
            embedding_provider=DeterministicEmbeddingProvider(),
            collection_name="polluted_collection",
        )


def test_eval_run_can_prebuild_shared_milvus_index(monkeypatch) -> None:
    """eval run 级预建 index 会消费 Milvus 配置，并返回可写入报告的 metadata。"""

    from app.core.config import get_settings
    from eval.run_eval import _build_eval_schema_vector_index

    fake_module = _install_fake_pymilvus(monkeypatch, row_count=None)
    monkeypatch.setenv("SCHEMA_VECTOR_BACKEND", "milvus")
    monkeypatch.setenv("SCHEMA_EMBEDDING_PROVIDER", "deterministic")
    monkeypatch.setenv("MILVUS_COLLECTION", "m20_unit_unique")
    get_settings.cache_clear()
    try:
        index, metadata = _build_eval_schema_vector_index(pipeline_mode="new_text2sql")
    finally:
        get_settings.cache_clear()

    assert index is not None
    assert metadata["schema_vector_index_reuse"] == "run_scoped"
    # M30 将 knowledge_docs 的 9 个字段文档从 Text2SQL corpus 隔离：195 -> 186。
    assert metadata["schema_docs_count"] == 186
    assert metadata["milvus_collection"] == "m20_unit_unique"
    assert metadata["result_match_oracle_backend"] == "sqlite_deterministic_seed"
    assert fake_module.MilvusClient.insert_calls == 1


def _install_fake_pymilvus(monkeypatch, *, row_count: int | None, schema_docs_hash: str | None = None):
    """安装最小 fake pymilvus 模块，避免单元测试依赖 Docker。"""

    class FakeDataType:
        VARCHAR = "VARCHAR"
        FLOAT_VECTOR = "FLOAT_VECTOR"

    class FakeSchema:
        def add_field(self, *args, **kwargs) -> None:
            return None

    class FakeIndexParams:
        def add_index(self, *args, **kwargs) -> None:
            return None

    class FakeMilvusClient:
        insert_calls = 0
        collections: set[str] = set()

        def __init__(self, *args, **kwargs) -> None:
            return None

        @staticmethod
        def create_schema(*args, **kwargs) -> FakeSchema:
            return FakeSchema()

        @staticmethod
        def prepare_index_params() -> FakeIndexParams:
            return FakeIndexParams()

        def has_collection(self, collection_name: str) -> bool:
            return row_count is not None or collection_name in self.collections

        def drop_collection(self, collection_name: str) -> None:
            self.collections.discard(collection_name)

        def create_collection(self, collection_name: str, *args, **kwargs) -> None:
            self.collections.add(collection_name)

        def get_collection_stats(self, collection_name: str) -> dict[str, int]:
            if row_count is None:
                return {"row_count": 0 if collection_name in self.collections else 0}
            return {"row_count": row_count}

        def describe_collection(self, collection_name: str) -> dict[str, object]:
            description = (
                f"datapilot_schema_docs_hash={schema_docs_hash}"
                if schema_docs_hash is not None
                else ""
            )
            return {
                "schema": {
                    "description": description,
                    "fields": [{"name": "vector", "params": {"dim": 128}}],
                }
            }

        def insert(self, collection_name: str, data: list[dict[str, object]]) -> None:
            type(self).insert_calls += 1
            self.collections.add(collection_name)

        def flush(self, *args, **kwargs) -> None:
            return None

        def load_collection(self, *args, **kwargs) -> None:
            return None

        def close(self) -> None:
            return None

    fake_module = SimpleNamespace(DataType=FakeDataType, MilvusClient=FakeMilvusClient)
    monkeypatch.setitem(sys.modules, "pymilvus", fake_module)
    return fake_module
