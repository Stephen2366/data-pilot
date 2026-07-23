"""M9 的向量索引边界。

当前自动化测试使用 deterministic in-memory index：它不依赖外部模型，却能稳定模拟“语义相近
文本更容易排前”的检索接口。Milvus adapter 只保留边界，避免在 M9 把任务扩大成 Docker /
依赖安装。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from engine.schema_retrieval.objects import SchemaDocument, SchemaHit

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class EmbeddingProvider(Protocol):
    """Embedding 协议：后续真实 BGE / text2vec / OpenAI embedding 都可以实现它。"""

    def embed(self, text: str) -> dict[str, float]:
        """把文本转成稀疏向量。"""


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
    """Milvus adapter 占位。

    M9 经用户确认不新增 `pymilvus` 或 Docker 依赖；真正接入时实现与 `InMemoryVectorIndex`
    相同的 `search()` 契约即可。
    """

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """明确提示当前 adapter 尚未启用，防止 README 或测试误报 Milvus 已可用。"""

        raise NotImplementedError(
            "Milvus adapter is reserved for a later module; M9 uses InMemoryVectorIndex."
        )
