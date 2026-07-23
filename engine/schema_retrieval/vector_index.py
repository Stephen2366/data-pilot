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

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
DEFAULT_MILVUS_URI = "http://127.0.0.1:19530"
DEFAULT_MILVUS_DIMENSION = 128


class EmbeddingProvider(Protocol):
    """Embedding 协议：后续真实 BGE / text2vec / OpenAI embedding 都可以实现它。"""

    def embed(self, text: str) -> dict[str, float]:
        """把文本转成稀疏向量。"""


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
        self.dimension = dimension
        self._documents_by_id = {document.doc_id: document for document in documents}
        self._client = MilvusClient(uri=uri, timeout=timeout)

        if reset_collection and self._client.has_collection(collection_name):
            self._client.drop_collection(collection_name)
        if not self._client.has_collection(collection_name):
            schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("doc_id", DataType.VARCHAR, is_primary=True, max_length=512)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dimension)
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
            self._client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )

        # 步骤 1：写入向量并 flush，确保后续 search 能立即看到本轮实验文档。-------------
        rows = [
            {
                "doc_id": document.doc_id,
                "vector": self._to_dense_vector(self.embedding_provider.embed(document.vector_text)),
            }
            for document in documents
        ]
        if rows:
            self._client.insert(collection_name=collection_name, data=rows)
            self._client.flush(collection_name=collection_name)
        self._client.load_collection(collection_name)

    def _to_dense_vector(self, sparse_vector: dict[str, float]) -> list[float]:
        """把 M9 稀疏 embedding 哈希到固定维度 dense vector，供 Milvus FLOAT_VECTOR 使用。"""

        dense = [0.0] * self.dimension
        for token, value in sparse_vector.items():
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
