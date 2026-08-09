"""Schema Retriever：关键词召回 + 向量召回 + 可显式选择的融合实验。

默认 ``weighted`` 保留 M9 的稳定行为。M21 只增加 ``rrf`` 作为显式实验策略，用 retrieval-only
benchmark 验证“更好的 vector 召回是否能进入最终上下文”；它不读取任何 eval ``expected_*`` 标签，
避免把离线答案泄漏到线上排序。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import Settings, get_settings
from engine.nl2sql.schema_loader import DomainSchema
from engine.schema_retrieval.document_builder import DEFAULT_RELATIONS_PATH, build_schema_documents, schema_documents_hash
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider, SiliconFlowEmbeddingProvider
from engine.schema_retrieval.objects import SchemaDocument, SchemaHit, SchemaRetrievalResult
from engine.schema_retrieval.vector_index import (
    DEFAULT_MILVUS_DIMENSION,
    DeterministicEmbeddingProvider,
    InMemoryVectorIndex,
    MilvusVectorIndex,
    VectorIndex,
)

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
        # 字段文档会继承表别名；例如 ``orders_wide`` 的“渠道 GMV 看板”会让几十个字段都
        # 命中“渠道 GMV”。业务指标 key 被题面直接点名时额外提升，确保 gmv 这类定义进入
        # 局部 SchemaGraph，而不是被同表字段的重复别名挤出 top-k。
        score += 12.0
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


def _merge_hits(
    keyword_hits: list[SchemaHit],
    vector_hits: list[SchemaHit],
    *,
    top_k: int,
    fusion_strategy: str = "weighted",
) -> list[SchemaHit]:
    """合并 keyword/vector hits，并保持默认 weighted 排序不变。

    ``weighted`` 延续既有分数语义：关键词分数乘 1.2 后与向量分数相加；``rrf`` 只看两路名次，
    可避免不同 backend 的原始相似度尺度不可比。★ 这只是 M21 的实验开关，不能接收 case 的
    expected table / column / metric 等离线标签。
    """

    strategy = (fusion_strategy or "weighted").lower()
    if strategy not in {"weighted", "rrf"}:
        raise ValueError(f"Unsupported schema fusion strategy={fusion_strategy}.")

    by_doc: dict[str, tuple[SchemaDocument, float, float]] = {}
    for hit in keyword_hits:
        _doc, score, rrf = by_doc.get(hit.document.doc_id, (hit.document, 0.0, 0.0))
        by_doc[hit.document.doc_id] = (hit.document, score + hit.score * 1.2, rrf + 1 / (60 + hit.rank))
    for hit in vector_hits:
        _doc, score, rrf = by_doc.get(hit.document.doc_id, (hit.document, 0.0, 0.0))
        by_doc[hit.document.doc_id] = (hit.document, score + hit.score, rrf + 1 / (60 + hit.rank))

    # 步骤 1：只在候选 hit 的线上可得分数 / rank 上计算融合分 -------------------------------
    # weighted 沿用 M9 既有行为；RRF 不混用 keyword 与 vector 的原始分数，便于跨 backend 对照。
    def fusion_score(item: tuple[SchemaDocument, float, float]) -> float:
        _document, weighted_score, rrf_score = item
        return weighted_score + rrf_score if strategy == "weighted" else rrf_score

    ranked = sorted(by_doc.values(), key=lambda item: (-fusion_score(item), item[0].doc_id))[:top_k]
    return [
        SchemaHit(
            document=document,
            score=fusion_score((document, score, rrf_score)),
            source="merged",
            rank=index,
            doc_type=document.doc_type,
            rrf_score=rrf_score,
        )
        for index, (document, score, rrf_score) in enumerate(ranked, start=1)
    ]


def _build_embedding_provider(settings: Settings, *, provider_override: str | None = None):
    """按配置创建 embedding provider；默认不联网。"""

    provider = (provider_override or settings.schema_embedding_provider).lower()
    if provider == "deterministic":
        return DeterministicEmbeddingProvider()
    if provider == "siliconflow":
        return SiliconFlowEmbeddingProvider(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url or "https://api.siliconflow.cn/v1",
            model=settings.siliconflow_embedding_model,
            dimensions=settings.siliconflow_embedding_dimensions,
        )
    if provider in {"dashscope", "qwen"}:
        return DashScopeEmbeddingProvider(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_embedding_base_url,
            model=settings.qwen_embedding_model,
            dimensions=settings.qwen_embedding_dimensions,
        )
    raise ValueError(f"Unsupported SCHEMA_EMBEDDING_PROVIDER={settings.schema_embedding_provider}.")


def _configured_milvus_dimension(settings: Settings, *, provider_override: str | None = None) -> int:
    """按 embedding provider 选择 Milvus dense vector 维度。"""

    provider = (provider_override or settings.schema_embedding_provider).lower()
    if provider in {"dashscope", "qwen"}:
        return settings.qwen_embedding_dimensions
    return settings.siliconflow_embedding_dimensions or DEFAULT_MILVUS_DIMENSION


def build_configured_vector_index(
    documents: list[SchemaDocument],
    *,
    schema_retrieval_profile: str = "default",
) -> VectorIndex:
    """根据显式配置创建向量索引；默认保持 M9 的本地 deterministic 路径。"""

    settings = get_settings()
    profile = (schema_retrieval_profile or "default").lower()
    if profile == "milvus_qwen37":
        backend = "milvus"
        provider_name = "dashscope"
    elif profile == "default":
        backend = settings.schema_vector_backend.lower()
        provider_name = settings.schema_embedding_provider.lower()
    else:
        raise ValueError(f"Unsupported schema_retrieval_profile={schema_retrieval_profile}.")

    embedding_provider = _build_embedding_provider(settings, provider_override=provider_name)

    if backend == "inmemory":
        if provider_name != "deterministic":
            raise ValueError("SCHEMA_VECTOR_BACKEND=inmemory 只支持 SCHEMA_EMBEDDING_PROVIDER=deterministic。")
        return InMemoryVectorIndex(documents=documents, embedding_provider=embedding_provider)
    if backend == "milvus":
        return MilvusVectorIndex(
            documents=documents,
            embedding_provider=embedding_provider,
            collection_name=settings.milvus_collection,
            uri=settings.milvus_uri,
            dimension=_configured_milvus_dimension(settings, provider_override=provider_name),
            reset_collection=settings.milvus_reset_collection,
        )
    raise ValueError(f"Unsupported SCHEMA_VECTOR_BACKEND={settings.schema_vector_backend}.")


# 兼容旧测试/旧脚本里可能直接 import 私有函数的用法；新代码优先用 public 名称。
_build_configured_vector_index = build_configured_vector_index


def build_configured_schema_vector_index(
    *,
    domain_schema: DomainSchema,
    relations_path: Path = DEFAULT_RELATIONS_PATH,
    schema_retrieval_profile: str = "default",
) -> tuple[VectorIndex, list[SchemaDocument], str]:
    """构建可在一个 eval run 内复用的 Schema vector index。

    ★ M20 前 `retrieve_schema()` 每个 case 都会隐式重建 Milvus index，导致同一批 schema docs
    被反复写入固定 collection。这个函数让 eval runner 在 run 开始时显式建一次，再通过
    `vector_index` 参数传给每个请求；默认 in-memory 路径仍可不使用它。
    """

    documents = build_schema_documents(domain_schema, relations_path=relations_path)
    vector_index = build_configured_vector_index(
        documents,
        schema_retrieval_profile=schema_retrieval_profile,
    )
    return vector_index, documents, schema_documents_hash(documents)


def retrieve_schema(
    *,
    question: str,
    user_role: str,
    top_k: int,
    domain_schema: DomainSchema,
    relations_path: Path = DEFAULT_RELATIONS_PATH,
    vector_index: VectorIndex | None = None,
    schema_retrieval_profile: str = "default",
    fusion_strategy: str = "weighted",
) -> SchemaRetrievalResult:
    """★ 对一个自然语言问题召回局部 Schema 文档。

    ``fusion_strategy`` 默认 ``weighted``，因此老调用方和默认 pipeline 不变；``rrf`` 必须由
    benchmark、eval CLI 或 API 请求显式传入，作为 M21 的受控实验路径。
    """

    documents = build_schema_documents(domain_schema, relations_path=relations_path)
    keyword_hits = _keyword_search(question, documents, top_k=top_k)
    active_vector_index = vector_index or build_configured_vector_index(
        documents,
        schema_retrieval_profile=schema_retrieval_profile,
    )
    vector_hits = active_vector_index.search(question, top_k=top_k)
    merged_hits = _merge_hits(keyword_hits, vector_hits, top_k=top_k, fusion_strategy=fusion_strategy)
    return SchemaRetrievalResult(
        question=question,
        user_role=user_role,
        keyword_hits=keyword_hits,
        vector_hits=vector_hits,
        merged_hits=merged_hits,
    )
