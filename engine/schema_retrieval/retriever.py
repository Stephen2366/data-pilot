"""Schema Retriever：关键词召回 + 向量召回 + 简单融合。

M9 的 P0 要求是两路召回都存在、结果字段稳定；RRF / rerank 暂不做复杂实现，只在数据结构里
预留分数字段，后续相似字段混淆明显时再升级。
"""

from __future__ import annotations

import re
from pathlib import Path

from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.document_builder import DEFAULT_RELATIONS_PATH, build_schema_documents
from engine.schema_retrieval.objects import SchemaDocument, SchemaHit, SchemaRetrievalResult
from engine.schema_retrieval.vector_index import DeterministicEmbeddingProvider, InMemoryVectorIndex, VectorIndex

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}|[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """把中英文问题切成关键词；中文保留单字与连续短语。"""

    normalized = text.lower()
    raw_tokens = TOKEN_RE.findall(normalized)
    tokens = list(raw_tokens)
    for raw_token in raw_tokens:
        chinese_chars = [char for char in raw_token if "\u4e00" <= char <= "\u9fff"]
        tokens.extend(chinese_chars)
        for size in (2, 3, 4):
            for index in range(len(chinese_chars) - size + 1):
                tokens.append("".join(chinese_chars[index : index + size]))
    return [token for token in tokens if token.strip()]


def _keyword_score(question: str, document: SchemaDocument) -> float:
    """计算轻量关键词分数，精确字段 / 指标名命中会额外加权。"""

    haystack = document.keyword_text.lower()
    score = 0.0
    for token in set(_tokens(question)):
        if token in haystack:
            score += max(0.2, min(len(token), 8) / 4)
    if document.table and document.table.lower() in question.lower():
        score += 2.0
    if document.column and document.column.lower() in question.lower():
        score += 2.0
    if document.metric_key and document.metric_key.lower() in question.lower():
        score += 2.0
    return score


def _keyword_search(question: str, documents: list[SchemaDocument], *, top_k: int) -> list[SchemaHit]:
    """关键词召回入口。"""

    scored = [(document, _keyword_score(question, document)) for document in documents]
    ranked = sorted(scored, key=lambda item: (-item[1], item[0].doc_id))[:top_k]
    return [
        SchemaHit(
            document=document,
            score=score,
            source="keyword",
            rank=index,
            doc_type=document.doc_type,
        )
        for index, (document, score) in enumerate(ranked, start=1)
        if score > 0
    ]


def _merge_hits(keyword_hits: list[SchemaHit], vector_hits: list[SchemaHit], *, top_k: int) -> list[SchemaHit]:
    """简单融合两路召回：同一 doc 取加权分，保留 RRF 扩展位。"""

    by_doc: dict[str, tuple[SchemaDocument, float, float]] = {}
    for hit in keyword_hits:
        _doc, score, rrf = by_doc.get(hit.document.doc_id, (hit.document, 0.0, 0.0))
        by_doc[hit.document.doc_id] = (hit.document, score + hit.score * 1.2, rrf + 1 / (60 + hit.rank))
    for hit in vector_hits:
        _doc, score, rrf = by_doc.get(hit.document.doc_id, (hit.document, 0.0, 0.0))
        by_doc[hit.document.doc_id] = (hit.document, score + hit.score, rrf + 1 / (60 + hit.rank))

    ranked = sorted(by_doc.values(), key=lambda item: (-(item[1] + item[2]), item[0].doc_id))[:top_k]
    return [
        SchemaHit(
            document=document,
            score=score + rrf_score,
            source="merged",
            rank=index,
            doc_type=document.doc_type,
            rrf_score=rrf_score,
        )
        for index, (document, score, rrf_score) in enumerate(ranked, start=1)
    ]


def retrieve_schema(
    *,
    question: str,
    user_role: str,
    top_k: int,
    domain_schema: DomainSchema,
    relations_path: Path = DEFAULT_RELATIONS_PATH,
    vector_index: VectorIndex | None = None,
) -> SchemaRetrievalResult:
    """★ 对一个自然语言问题召回局部 Schema 文档。"""

    documents = build_schema_documents(domain_schema, relations_path=relations_path)
    keyword_hits = _keyword_search(question, documents, top_k=top_k)
    active_vector_index = vector_index or InMemoryVectorIndex(
        documents=documents,
        embedding_provider=DeterministicEmbeddingProvider(),
    )
    vector_hits = active_vector_index.search(question, top_k=top_k)
    merged_hits = _merge_hits(keyword_hits, vector_hits, top_k=top_k)
    return SchemaRetrievalResult(
        question=question,
        user_role=user_role,
        keyword_hits=keyword_hits,
        vector_hits=vector_hits,
        merged_hits=merged_hits,
    )
