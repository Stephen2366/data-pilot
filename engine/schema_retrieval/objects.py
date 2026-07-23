"""Schema Retrieval 的核心数据结构。

这些结构刻意保持轻量：M9 只负责“召回和解释上下文”，不提前承担 M10 QueryPlan 或 M11 SQL
生成职责。字段里预留 score/source/rank/rerank 等信息，是为了后续接 Milvus、RRF 和 rerank
时不用重写评测契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SchemaDocType = Literal["field_doc", "metric_doc", "relation_doc"]


@dataclass(frozen=True)
class SchemaDocument:
    """一段可检索的 Schema 知识。

    `keyword_text` 面向关键词召回，尽量包含表字段名、中文业务描述和常见说法；
    `vector_text` 面向向量召回，允许更完整、更口语化。
    """

    doc_id: str
    doc_type: SchemaDocType
    table: str | None
    column: str | None
    metric_key: str | None
    relation: dict[str, Any] | None
    keyword_text: str
    vector_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaHit:
    """一次召回命中的文档及其排序信息。"""

    document: SchemaDocument
    score: float
    source: str
    rank: int
    doc_type: SchemaDocType
    rrf_score: float | None = None
    rerank_score: float | None = None
    rerank_reason: str | None = None


@dataclass(frozen=True)
class SchemaRetrievalResult:
    """Schema Retrieval 的三段输出：关键词、向量、融合结果。"""

    question: str
    user_role: str
    keyword_hits: list[SchemaHit]
    vector_hits: list[SchemaHit]
    merged_hits: list[SchemaHit]


@dataclass(frozen=True)
class JoinEdge:
    """JoinPath 中的一条边，所有条件都来自 `relations.yaml`。"""

    relation_id: str
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    join_type: str
    source: str = "relations.yaml"
    through_table: str | None = None
    warning: str | None = None


@dataclass(frozen=True)
class JoinPath:
    """连接当前问题相关表的一条轻量路径。"""

    tables: list[str]
    edges: list[JoinEdge]


@dataclass(frozen=True)
class SchemaGraph:
    """当前问题的局部 Schema 视图。

    `tables` 是后续 prompt 可见表集合；`fields` 只按表收纳字段名，M10/M11 再决定怎样展示。
    """

    tables: list[str]
    fields: dict[str, list[str]]
    metrics: list[str]
    relations: list[dict[str, Any]]
    join_paths: list[JoinPath]

    @property
    def field_names(self) -> list[str]:
        """返回去重后的扁平字段名，方便 eval 统计 expected_columns 召回。"""

        return sorted({field for columns in self.fields.values() for field in columns})
