"""M34 EnterpriseRAG 的独立 DashScope embedding + Milvus semantic candidate。

构建按 SQLite row_id 流式读取、每批 embedding 后立即 upsert 并清缓存；中断只留下
``building`` checkpoint，不产生 candidate manifest。相同 identity 可按 Milvus row count 恢复。
"""

from __future__ import annotations

import json
import os
import sqlite3
from http.client import IncompleteRead
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from time import perf_counter, sleep
from typing import Any
from urllib.error import HTTPError, URLError
from uuid import uuid4

from engine.governance import OutboundPolicy, OutboundRule
from engine.rag.catalog import CatalogEntry
from engine.rag.enterprise_dataset import canonical_identity
from engine.rag.enterprise_profile import ExternalProfileManifest, verify_external_profile
from engine.rag.retrieval import RetrievalAdapterError, RetrievalBatch, RetrievalMatch, query_fingerprint
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider

SEMANTIC_FORMAT = "enterprise-knowledge-semantic-v1"
SEMANTIC_ADAPTER_IDENTITY = "knowledge-enterprise-milvus-semantic-v1"
SEMANTIC_RECIPE_IDENTITY = "qwen-dense-cosine-dedup-physical-v1"
KNOWLEDGE_EMBEDDING_OUTBOUND_IDENTITY = "knowledge-enterprise-embedding-outbound-v1"
KNOWLEDGE_EMBEDDING_POLICY = OutboundPolicy(
    identity=KNOWLEDGE_EMBEDDING_OUTBOUND_IDENTITY,
    rules=(
        OutboundRule(
            "dashscope_embedding",
            "knowledge_embedding",
            "public_benchmark_document",
            frozenset({"texts", "model", "dimensions"}),
        ),
    ),
)
KNOWLEDGE_GENERATION_POLICY = OutboundPolicy(
    identity="knowledge-enterprise-generation-outbound-v1",
    rules=(
        OutboundRule(
            "qwen_chat",
            "knowledge_answer_generation",
            "public_benchmark_document",
            frozenset({"prompt", "system_prompt", "model"}),
        ),
    ),
)
_DESCRIPTION_PREFIX = "enterprise-semantic-identity:"


@dataclass(frozen=True)
class EnterpriseSemanticManifest:
    format: str
    lifecycle_status: str
    semantic_identity: str
    profile_identity: str
    corpus_identity: str
    unit_recipe_identity: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    outbound_policy_identity: str
    collection_name: str
    milvus_uri: str
    unit_count: int
    unit_set_identity: str
    build_seconds: float
    manifest_identity: str

    def unsigned_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("manifest_identity")
        return value


def _semantic_identity(profile: ExternalProfileManifest, model: str, dimensions: int) -> str:
    return canonical_identity(
        {
            "format": SEMANTIC_FORMAT,
            "profile_identity": profile.profile_identity,
            "corpus_identity": profile.corpus_identity,
            "unit_recipe_identity": profile.unit_recipe_identity,
            "adapter_identity": SEMANTIC_ADAPTER_IDENTITY,
            "recipe_identity": SEMANTIC_RECIPE_IDENTITY,
            "embedding_provider": "dashscope",
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "outbound_policy_identity": KNOWLEDGE_EMBEDDING_OUTBOUND_IDENTITY,
        }
    )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_checkpoint(path: Path, identity: str, collection: str) -> int | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["semantic_identity"] != identity or payload["collection_name"] != collection:
            raise ValueError("checkpoint identity mismatch")
        return int(payload["completed_units"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RetrievalAdapterError("semantic_checkpoint_invalid", str(exc)) from exc


def _row_count(client: Any, collection_name: str) -> int:
    raw = client.get_collection_stats(collection_name=collection_name).get("row_count")
    if raw is None:
        raise RetrievalAdapterError("semantic_collection_invalid", "Milvus row_count unavailable")
    return int(raw)


def _unit_set_identity(values: set[str]) -> str:
    digest = sha256()
    for value in sorted(values):
        digest.update(value.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _milvus_unit_set(client: Any, collection_name: str) -> tuple[int, str]:
    """按可见主键去重闭合；不使用包含 tombstone 的物理 row count。"""

    iterator = client.query_iterator(
        collection_name=collection_name,
        batch_size=2000,
        output_fields=["unit_identity"],
    )
    identities: set[str] = set()
    try:
        while True:
            rows = iterator.next()
            if not rows:
                break
            identities.update(str(row["unit_identity"]) for row in rows)
    finally:
        iterator.close()
    return len(identities), _unit_set_identity(identities)


def _ensure_collection(client: Any, collection_name: str, identity: str, dimensions: int) -> None:
    from pymilvus import DataType, MilvusClient

    if client.has_collection(collection_name):
        description = client.describe_collection(collection_name=collection_name).get("description", "")
        if description != f"{_DESCRIPTION_PREFIX}{identity}":
            raise RetrievalAdapterError("semantic_collection_identity_mismatch", collection_name)
        return
    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=False,
        description=f"{_DESCRIPTION_PREFIX}{identity}",
    )
    schema.add_field("unit_identity", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dimensions)
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(field_name="vector", metric_type="COSINE", index_type="AUTOINDEX")
    client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)


def _embed_with_retry(
    provider: DashScopeEmbeddingProvider,
    texts: list[str],
    *,
    max_attempts: int = 6,
) -> list[list[float]]:
    """只重试瞬时 transport 故障；认证/合同错误保持立即失败关闭。"""

    for attempt in range(1, max_attempts + 1):
        try:
            return provider.embed_texts(texts)
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == max_attempts:
                try:
                    payload = json.loads(exc.read().decode("utf-8", errors="replace"))
                    safe_error = {
                        key: payload.get(key)
                        for key in ("code", "message", "request_id")
                        if isinstance(payload, dict) and payload.get(key) is not None
                    }
                except (OSError, ValueError, json.JSONDecodeError):
                    safe_error = {"status": exc.code, "reason": exc.reason}
                raise RetrievalAdapterError(
                    "embedding_request_rejected", json.dumps(safe_error, ensure_ascii=False)
                ) from exc
        except (URLError, TimeoutError, ConnectionError, IncompleteRead):
            if attempt == max_attempts:
                raise
        provider.clear_cache()
        sleep(min(2 ** (attempt - 1), 30))
    raise AssertionError("unreachable")


def build_enterprise_semantic_candidate(
    *,
    profile_root: Path,
    profile_identity: str,
    semantic_root: Path,
    provider: DashScopeEmbeddingProvider,
    parallel_providers: tuple[DashScopeEmbeddingProvider, ...] = (),
    milvus_uri: str,
    model: str,
    dimensions: int,
    max_units: int | None = None,
) -> dict[str, Any]:
    """流式构建或恢复；``max_units`` 只用于 provider smoke，不会生成 candidate manifest。"""

    from pymilvus import MilvusClient

    profile = verify_external_profile(root=profile_root, profile_identity=profile_identity)
    identity = _semantic_identity(profile, model, dimensions)
    collection = f"datapilot_knowledge_enterprise_{identity[:24]}"
    target = semantic_root / identity
    manifest_path = target / "semantic.json"
    if manifest_path.is_file():
        manifest = load_enterprise_semantic_manifest(semantic_root=semantic_root, semantic_identity=identity)
        return {"status": "candidate", "manifest": asdict(manifest)}

    client = MilvusClient(uri=milvus_uri, timeout=30)
    started = perf_counter()
    try:
        collection_existed = client.has_collection(collection)
        _ensure_collection(client, collection, identity, dimensions)
        checkpoint_path = semantic_root / f".building-{identity}.json"
        checkpoint_completed = _load_checkpoint(checkpoint_path, identity, collection)
        if checkpoint_completed is None:
            if collection_existed and _row_count(client, collection) != 0:
                raise RetrievalAdapterError(
                    "semantic_checkpoint_missing", "non-empty collection cannot infer logical cursor"
                )
            completed = 0
        else:
            completed = checkpoint_completed
        database = profile_root / profile_identity / profile.database_file
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        expected_unit_identity = _unit_set_identity(
            {str(row[0]) for row in connection.execute("SELECT unit_identity FROM units")}
        )
        stop_at = profile.unit_count if max_units is None else min(profile.unit_count, completed + max_units)
        providers = (provider, *parallel_providers)
        while completed < stop_at:
            rows = connection.execute(
                "SELECT row_id, unit_identity, content FROM units WHERE row_id > ? ORDER BY row_id LIMIT ?",
                (completed, min(20 * len(providers), stop_at - completed)),
            ).fetchall()
            if not rows:
                break
            text_batches = [
                [str(row["content"]) for row in rows[index : index + 20]]
                for index in range(0, len(rows), 20)
            ]
            with ThreadPoolExecutor(max_workers=len(text_batches)) as executor:
                futures = [
                    executor.submit(_embed_with_retry, providers[index], texts)
                    for index, texts in enumerate(text_batches)
                ]
                vectors = [vector for future in futures for vector in future.result()]
            client.upsert(
                collection_name=collection,
                data=[
                    {"unit_identity": str(row["unit_identity"]), "vector": vector}
                    for row, vector in zip(rows, vectors, strict=True)
                ],
            )
            for active_provider in providers:
                active_provider.clear_cache()
            completed = int(rows[-1]["row_id"])
            _atomic_json(
                checkpoint_path,
                {
                    "semantic_identity": identity,
                    "collection_name": collection,
                    "completed_units": completed,
                    "expected_units": profile.unit_count,
                    "request_count": sum(active.request_count for active in providers),
                    "total_tokens": sum(active.total_tokens for active in providers),
                },
            )
        connection.close()
        client.flush(collection_name=collection)
        physical_row_count = _row_count(client, collection)
        if max_units is not None or completed < profile.unit_count:
            return {
                "status": "building",
                "semantic_identity": identity,
                "collection_name": collection,
                "completed_units": completed,
                "milvus_physical_row_count": physical_row_count,
                "expected_units": profile.unit_count,
                "request_count": sum(active.request_count for active in providers),
                "total_tokens": sum(active.total_tokens for active in providers),
            }
        visible_count, visible_identity = _milvus_unit_set(client, collection)
        if visible_count != profile.unit_count or visible_identity != expected_unit_identity:
            raise RetrievalAdapterError(
                "semantic_collection_unit_set_mismatch",
                f"visible={visible_count}/{profile.unit_count}",
            )
        unsigned = {
            "format": SEMANTIC_FORMAT,
            "lifecycle_status": "candidate",
            "semantic_identity": identity,
            "profile_identity": profile.profile_identity,
            "corpus_identity": profile.corpus_identity,
            "unit_recipe_identity": profile.unit_recipe_identity,
            "embedding_provider": "dashscope",
            "embedding_model": model,
            "embedding_dimensions": dimensions,
            "outbound_policy_identity": KNOWLEDGE_EMBEDDING_OUTBOUND_IDENTITY,
            "collection_name": collection,
            "milvus_uri": milvus_uri,
            "unit_count": profile.unit_count,
            "unit_set_identity": visible_identity,
            "build_seconds": round(perf_counter() - started, 6),
        }
        manifest = EnterpriseSemanticManifest(**unsigned, manifest_identity=canonical_identity(unsigned))
        _atomic_json(manifest_path, asdict(manifest))
        building = checkpoint_path
        if building.exists():
            building.unlink()
        return {"status": "candidate", "manifest": asdict(manifest)}
    finally:
        client.close()


def load_enterprise_semantic_manifest(
    *, semantic_root: Path, semantic_identity: str
) -> EnterpriseSemanticManifest:
    try:
        payload = json.loads((semantic_root / semantic_identity / "semantic.json").read_text(encoding="utf-8"))
        manifest = EnterpriseSemanticManifest(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RetrievalAdapterError("semantic_manifest_invalid", str(exc)) from exc
    if canonical_identity(manifest.unsigned_payload()) != manifest.manifest_identity:
        raise RetrievalAdapterError("semantic_manifest_hash_mismatch", semantic_identity)
    return manifest


class EnterpriseMilvusSemanticAdapter:
    """只消费 Knowledge Tool 已授权 entries，并按物理文档去重。"""

    identity = SEMANTIC_ADAPTER_IDENTITY
    recipe_identity = SEMANTIC_RECIPE_IDENTITY

    def __init__(self, *, manifest: EnterpriseSemanticManifest, provider: DashScopeEmbeddingProvider) -> None:
        from pymilvus import MilvusClient

        self._manifest = manifest
        self._provider = provider
        self._lock = RLock()
        self._closed = False
        self._client = MilvusClient(uri=manifest.milvus_uri, timeout=30)
        try:
            if not self._client.has_collection(collection_name=manifest.collection_name):
                raise RetrievalAdapterError(
                    "semantic_collection_missing", manifest.collection_name
                )
            description = self._client.describe_collection(
                collection_name=manifest.collection_name
            ).get("description", "")
            if description != f"{_DESCRIPTION_PREFIX}{manifest.semantic_identity}":
                raise RetrievalAdapterError(
                    "semantic_collection_identity_mismatch", manifest.collection_name
                )
            # ★ Milvus 重启后的 collection 可能仍存在但尚未 load。query_iterator 和 search
            # 都要求 collection 已 load，所以冷启动顺序必须先 load/readiness，再核对 unit set。
            self._client.load_collection(collection_name=manifest.collection_name)
            load_state = self._client.get_load_state(collection_name=manifest.collection_name)
            if "Loaded" not in str(load_state.get("state")):
                raise RetrievalAdapterError(
                    "semantic_collection_not_loaded", manifest.collection_name
                )
            visible_count, visible_identity = _milvus_unit_set(
                self._client, manifest.collection_name
            )
            if visible_count != manifest.unit_count or visible_identity != manifest.unit_set_identity:
                raise RetrievalAdapterError(
                    "semantic_collection_unit_set_mismatch", manifest.collection_name
                )
        except RetrievalAdapterError:
            self._client.close()
            self._closed = True
            raise
        except Exception as exc:
            self._client.close()
            self._closed = True
            raise RetrievalAdapterError(
                "semantic_runtime_unavailable", type(exc).__name__
            ) from exc

    def retrieve(self, *, question: str, confirmed_conditions: tuple[str, ...] = (), entries: tuple[CatalogEntry, ...], limit: int) -> RetrievalBatch:
        fingerprint = query_fingerprint(question, confirmed_conditions)
        if not entries:
            return RetrievalBatch(self.identity, self.recipe_identity, fingerprint, ())
        allowed = {entry.document_key.removeprefix("enterprise-unit:"): entry for entry in entries}
        query = "\n".join((question, *confirmed_conditions))
        # ★ provider 带可变 cache/counter，MilvusClient 也由 lifespan 共享。首版用一把锁
        # 串行化一次完整 search，宁可明确吞吐边界，也不制造跨请求向量/usage 串线。
        try:
            with self._lock:
                vector = _embed_with_retry(self._provider, [query])[0]
                self._provider.clear_cache()
                results = self._client.search(
                    collection_name=self._manifest.collection_name,
                    data=[vector],
                    limit=max(200, limit * 20),
                    output_fields=["unit_identity"],
                    anns_field="vector",
                )
        except RetrievalAdapterError:
            raise
        except Exception as exc:
            raise RetrievalAdapterError("semantic_retrieval_unavailable", type(exc).__name__) from exc
        selected: list[tuple[CatalogEntry, float]] = []
        seen_physical: set[str] = set()
        for item in results[0]:
            entity = item.get("entity") or {}
            unit_identity = str(entity.get("unit_identity") or item.get("id") or "")
            entry = allowed.get(unit_identity)
            if entry is None or entry.source_key in seen_physical:
                continue
            seen_physical.add(entry.source_key)
            selected.append((entry, max(float(item.get("distance", 0.0)) + 1.0, 1e-12)))
            if len(selected) >= limit:
                break
        return RetrievalBatch(
            self.identity,
            self.recipe_identity,
            fingerprint,
            tuple(
                RetrievalMatch(entry.document_key, entry.revision, entry.content_identity, entry.anchor, score, rank)
                for rank, (entry, score) in enumerate(selected, start=1)
            ),
        )

    def close(self) -> None:
        """幂等关闭共享 client；不 release collection，不改变外部索引状态。"""

        if not self._closed:
            self._client.close()
            self._closed = True


def load_enterprise_semantic_runtime(
    *,
    profile_root: Path,
    profile_identity: str,
    semantic_root: Path,
    semantic_identity: str,
    query_provider: DashScopeEmbeddingProvider,
    allow_cross_thread: bool = False,
):
    """把 semantic adapter 注入同一个 external bundle/context loader，不复制 Tool/AnswerFlow。"""

    from engine.rag.enterprise_runtime import load_enterprise_profile_runtime

    manifest = load_enterprise_semantic_manifest(
        semantic_root=semantic_root, semantic_identity=semantic_identity
    )
    if manifest.profile_identity != profile_identity:
        raise RetrievalAdapterError("semantic_profile_identity_mismatch", profile_identity)
    if (
        query_provider.model != manifest.embedding_model
        or query_provider.dimensions != manifest.embedding_dimensions
    ):
        raise RetrievalAdapterError("semantic_query_embedding_mismatch", semantic_identity)
    runtime = load_enterprise_profile_runtime(
        root=profile_root,
        profile_identity=profile_identity,
        allow_cross_thread=allow_cross_thread,
    )
    try:
        if (
            manifest.corpus_identity != runtime.bundle.corpus_identity
            or manifest.unit_recipe_identity != runtime.bundle.unit_recipe_identity
        ):
            raise RetrievalAdapterError(
                "semantic_profile_snapshot_mismatch", semantic_identity
            )
        runtime.adapter = EnterpriseMilvusSemanticAdapter(
            manifest=manifest, provider=query_provider
        )
        return runtime
    except Exception:
        runtime.close()
        raise
