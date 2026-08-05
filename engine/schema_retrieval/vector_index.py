"""M9 的向量索引边界。

当前自动化测试使用 deterministic in-memory index：它不依赖外部模型，却能稳定模拟“语义相近
文本更容易排前”的检索接口。Milvus adapter 只保留边界，避免在 M9 把任务扩大成 Docker /
依赖安装。
"""

from __future__ import annotations

import math
import re
from hashlib import sha1
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from engine.schema_retrieval.objects import SchemaDocument, SchemaHit
from engine.schema_retrieval.document_builder import schema_documents_hash

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
DEFAULT_MILVUS_URI = "http://127.0.0.1:19530"
DEFAULT_MILVUS_DIMENSION = 128
SCHEMA_DOCS_HASH_DESCRIPTION_PREFIX = "datapilot_schema_docs_hash="
EmbeddingVector = dict[str, float] | list[float]


class EmbeddingProvider(Protocol):
    """Embedding 协议：后续真实 BGE / text2vec / OpenAI embedding 都可以实现它。"""

    def embed(self, text: str) -> EmbeddingVector:
        """把文本转成稀疏或稠密向量。"""


class VectorIndex(Protocol):
    """向量索引协议：in-memory 与 Milvus 都只需要实现 search。"""

    def search(self, query: str, *, top_k: int) -> list[SchemaHit]:
        """按相似度返回 SchemaHit。"""


class DeterministicEmbeddingProvider:
    """不联网、不下载模型的确定性稀疏 embedding。"""

    def embed(self, text: str) -> dict[str, float]:
        """用 token 与中文 bigram 构造可重复向量。"""

        normalized = text.lower()
        tokens = TOKEN_RE.findall(normalized)
        features: Counter[str] = Counter(tokens)
        chinese_chars = [token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
        for index in range(len(chinese_chars) - 1):
            features["".join(chinese_chars[index : index + 2])] += 1
        return dict(features)


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    """计算稀疏向量余弦相似度。"""

    common = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


@dataclass
class InMemoryVectorIndex:
    """进程内向量索引，服务 M9 pytest 和本地诊断。"""

    documents: list[SchemaDocument]
    embedding_provider: EmbeddingProvider

    def __post_init__(self) -> None:
        """预计算文档向量，避免每次查询重复构建。"""

        self._vectors = {
            document.doc_id: self.embedding_provider.embed(document.vector_text)
            for document in self.documents
        }

    def search(self, query: str, *, top_k: int) -> list[SchemaHit]:
        """按 cosine 分数返回向量召回结果。"""

        query_vector = self.embedding_provider.embed(query)
        if not isinstance(query_vector, dict):
            raise TypeError("InMemoryVectorIndex only supports sparse dict embeddings.")
        scored = [
            (document, _cosine(query_vector, self._vectors[document.doc_id]))
            for document in self.documents
        ]
        ranked = sorted(scored, key=lambda item: (-item[1], item[0].doc_id))[:top_k]
        return [
            SchemaHit(
                document=document,
                score=score,
                source="vector",
                rank=index,
                doc_type=document.doc_type,
            )
            for index, (document, score) in enumerate(ranked, start=1)
            if score > 0
        ]


class MilvusVectorIndex:
    """Milvus adapter 实验实现。

    ★ M9.1 只在显式实例化时使用 Milvus；默认 retriever 仍走 in-memory，避免普通 pytest 或
    新同学本地启动被 Docker 服务绑住。
    """

    def __init__(
        self,
        *,
        documents: list[SchemaDocument],
        embedding_provider: EmbeddingProvider,
        collection_name: str,
        uri: str = DEFAULT_MILVUS_URI,
        dimension: int = DEFAULT_MILVUS_DIMENSION,
        reset_collection: bool = False,
        timeout: float = 10.0,
    ) -> None:
        """创建 Milvus collection 并写入 Schema 文档向量。"""

        try:
            from pymilvus import DataType, MilvusClient
        except ImportError as exc:
            raise RuntimeError("pymilvus is required for MilvusVectorIndex.") from exc

        self.documents = documents
        self.embedding_provider = embedding_provider
        self.collection_name = collection_name
        self._documents_by_id = {document.doc_id: document for document in documents}
        # ★ 行数只能发现“少写 / 重复写”，不能发现“文档数量没变但业务语义已变”。
        # 把内容 hash 放进 collection schema 的 description，才能安全复用同名 collection。
        self.schema_docs_hash = schema_documents_hash(documents)
        document_vectors = self._embed_texts([document.vector_text for document in documents])
        inferred_dimension = len(document_vectors[0]) if document_vectors and isinstance(document_vectors[0], list) else dimension
        self.dimension = inferred_dimension
        self._client = MilvusClient(uri=uri, timeout=timeout)
        self.inserted_document_count = 0
        self.initial_row_count: int | None = None
        self.final_row_count: int | None = None

        if reset_collection and self._client.has_collection(collection_name):
            self._client.drop_collection(collection_name)
        collection_exists = self._client.has_collection(collection_name)
        if not collection_exists:
            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=False,
                description=f"{SCHEMA_DOCS_HASH_DESCRIPTION_PREFIX}{self.schema_docs_hash}",
            )
            schema.add_field("doc_id", DataType.VARCHAR, is_primary=True, max_length=512)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.dimension)
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
            self._client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )
        else:
            self.initial_row_count = self._collection_row_count()
            existing_dimension = self._collection_vector_dimension()
            if existing_dimension is not None and existing_dimension != self.dimension:
                raise RuntimeError(
                    "Milvus collection vector dimension does not match current embedding: "
                    f"collection={collection_name} dimension={existing_dimension} expected={self.dimension}. "
                    "Use a unique MILVUS_COLLECTION or set MILVUS_RESET_COLLECTION=true."
                )
            if self.initial_row_count is not None and self.initial_row_count != len(documents):
                raise RuntimeError(
                    "Milvus collection is not clean for current schema docs: "
                    f"collection={collection_name} row_count={self.initial_row_count} "
                    f"expected={len(documents)}. Use a unique MILVUS_COLLECTION or set "
                    "MILVUS_RESET_COLLECTION=true for an explicit rebuild."
                )
            existing_schema_docs_hash = self._collection_schema_docs_hash()
            if existing_schema_docs_hash != self.schema_docs_hash:
                raise RuntimeError(
                    "Milvus collection schema document content hash does not match current documents: "
                    f"collection={collection_name} stored_hash={existing_schema_docs_hash or '<missing>'} "
                    f"expected_hash={self.schema_docs_hash}. Use a unique MILVUS_COLLECTION or set "
                    "MILVUS_RESET_COLLECTION=true for an explicit rebuild."
                )

        # 步骤 1：写入向量并 flush，确保后续 search 能立即看到本轮实验文档。-------------
        # M20/M23 索引卫生：只有“向量维度、文档内容 hash、行数”都匹配时才能复用。
        # 其中 hash 专门拦截“文档数量相同但语义文本已更新”的静默错配。
        should_insert = True
        if self.initial_row_count is not None:
            if self.initial_row_count == len(documents):
                should_insert = False
        elif collection_exists:
            raise RuntimeError(
                "Milvus collection already exists but row_count is unavailable: "
                f"collection={collection_name}. Use a unique MILVUS_COLLECTION or set "
                "MILVUS_RESET_COLLECTION=true before reusing it."
            )
        if should_insert:
            rows = [
                {
                    "doc_id": document.doc_id,
                    "vector": self._to_dense_vector(document_vector),
                }
                for document, document_vector in zip(
                    documents,
                    document_vectors,
                    strict=True,
                )
            ]
            if rows:
                self._client.insert(collection_name=collection_name, data=rows)
                self.inserted_document_count = len(rows)
                self._client.flush(collection_name=collection_name)
        self._client.load_collection(collection_name)
        self.final_row_count = self._collection_row_count()

    def _collection_row_count(self) -> int | None:
        """读取 Milvus collection 行数；旧 SDK 不支持时返回 None。

        `get_collection_stats()` 是 M20 smoke 的核心观测点。这里做兼容兜底，是为了不让
        pymilvus 小版本差异影响默认本地路径；真正的 Milvus 验收脚本会把 None 视为待排查。
        """

        get_stats = getattr(self._client, "get_collection_stats", None)
        if not callable(get_stats):
            return None
        stats = get_stats(collection_name=self.collection_name)
        raw_count = stats.get("row_count") if isinstance(stats, dict) else None
        if raw_count is None:
            return None
        return int(raw_count)

    def _collection_vector_dimension(self) -> int | None:
        """尽量读取已有 collection 的 vector 维度。"""

        describe = getattr(self._client, "describe_collection", None)
        if not callable(describe):
            return None
        payload = describe(collection_name=self.collection_name)
        if not isinstance(payload, dict):
            return None
        # pymilvus 版本差异：有的版本返回 ``schema.fields``，有的直接把 ``fields`` 放顶层。
        schema = payload.get("schema")
        fields = schema.get("fields", []) if isinstance(schema, dict) else payload.get("fields", [])
        for field in fields:
            if not isinstance(field, dict) or field.get("name") != "vector":
                continue
            params = field.get("params") or {}
            raw_dim = params.get("dim")
            return int(raw_dim) if raw_dim is not None else None
        return None

    def _collection_schema_docs_hash(self) -> str | None:
        """从 collection schema description 读取写入时的 Schema 文档内容 hash。

        M23 前创建的 collection 没有这个标记，即使行数和维度相同也必须视为不可安全复用；
        调用方可使用唯一 collection，或显式 reset 后由当前代码重建。
        """

        describe = getattr(self._client, "describe_collection", None)
        if not callable(describe):
            return None
        payload = describe(collection_name=self.collection_name)
        if not isinstance(payload, dict):
            return None
        # 同上，collection description 在不同 SDK 返回结构中的位置不同。
        schema = payload.get("schema")
        description = schema.get("description", "") if isinstance(schema, dict) else payload.get("description", "")
        if not isinstance(description, str) or not description.startswith(SCHEMA_DOCS_HASH_DESCRIPTION_PREFIX):
            return None
        return description.removeprefix(SCHEMA_DOCS_HASH_DESCRIPTION_PREFIX) or None

    def _embed_texts(self, texts: list[str]) -> list[EmbeddingVector]:
        """优先使用 provider 的 batch API，降低真实 embedding 请求次数。"""

        batch_embed = getattr(self.embedding_provider, "embed_texts", None)
        if callable(batch_embed):
            return list(batch_embed(texts))
        return [self.embedding_provider.embed(text) for text in texts]

    def _to_dense_vector(self, vector: EmbeddingVector) -> list[float]:
        """把 provider 输出统一成 Milvus FLOAT_VECTOR。"""

        if isinstance(vector, list):
            return [float(value) for value in vector]

        dense = [0.0] * self.dimension
        for token, value in vector.items():
            # ★ 不能用 Python 内置 hash()：它有进程级随机盐，会让 Milvus 实验召回排序不可复现。
            stable_index = int(sha1(token.encode("utf-8")).hexdigest(), 16) % self.dimension
            dense[stable_index] += value
        norm = math.sqrt(sum(value * value for value in dense))
        if norm == 0:
            return dense
        return [value / norm for value in dense]

    def search(self, query: str, *, top_k: int) -> list[SchemaHit]:
        """按 Milvus COSINE 相似度返回 SchemaHit。"""

        query_vector = self._to_dense_vector(self.embedding_provider.embed(query))
        results = self._client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=top_k,
            output_fields=["doc_id"],
            anns_field="vector",
        )
        hits: list[SchemaHit] = []
        for rank, item in enumerate(results[0], start=1):
            entity = item.get("entity") or {}
            doc_id = str(entity.get("doc_id") or item.get("id") or "")
            document = self._documents_by_id.get(doc_id)
            if document is None:
                continue
            hits.append(
                SchemaHit(
                    document=document,
                    score=float(item.get("distance", 0.0)),
                    source="milvus",
                    rank=rank,
                    doc_type=document.doc_type,
                )
            )
        return hits

    def drop_collection(self) -> None:
        """删除实验 collection，测试和 smoke 清理资源时使用。"""

        if self._client.has_collection(self.collection_name):
            self._client.drop_collection(self.collection_name)

    def close(self) -> None:
        """关闭 Milvus client 连接。"""

        self._client.close()
