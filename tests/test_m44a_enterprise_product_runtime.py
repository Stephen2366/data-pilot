"""M44A Enterprise product resolver 的默认、身份和零 fallback 合同。"""

from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from engine.rag.enterprise_product_runtime import (
    EnterpriseProductRuntimeConfig,
    load_enterprise_product_runtime,
)
from engine.rag.enterprise_semantic import (
    EnterpriseMilvusSemanticAdapter,
    EnterpriseSemanticManifest,
    load_enterprise_semantic_runtime,
)
from engine.rag.retrieval import RetrievalAdapterError
from eval.run_rag_external_eval import build_external_resolved_runtime


class _FakeRuntime:
    """只实现 product wrapper 需要的深 interface，避免单测访问真实 SQLite/Milvus。"""

    def __init__(self, *, adapter: str = "knowledge-enterprise-sqlite-lexical-v1") -> None:
        self.manifest = SimpleNamespace(profile_identity="profile-v1")
        self.bundle = SimpleNamespace(release_identity="profile-v1", corpus_identity="corpus-v1")
        self.adapter = SimpleNamespace(identity=adapter, recipe_identity="recipe-v1")
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _semantic_manifest() -> EnterpriseSemanticManifest:
    return EnterpriseSemanticManifest(
        format="enterprise-knowledge-semantic-v1",
        lifecycle_status="candidate",
        semantic_identity="semantic-v1",
        profile_identity="profile-v1",
        corpus_identity="corpus-v1",
        unit_recipe_identity="unit-recipe-v1",
        embedding_provider="dashscope",
        embedding_model="qwen3.7-text-embedding",
        embedding_dimensions=1024,
        outbound_policy_identity="policy-v1",
        collection_name="enterprise_collection_v1",
        milvus_uri="http://127.0.0.1:19530",
        unit_count=139214,
        unit_set_identity="unit-set-v1",
        build_seconds=1.0,
        manifest_identity="manifest-v1",
    )


def test_semantic_is_default_and_missing_snapshot_fails_before_any_fallback(monkeypatch) -> None:
    lexical_calls = 0

    def forbidden_lexical(**_kwargs):
        nonlocal lexical_calls
        lexical_calls += 1
        raise AssertionError("semantic failure must not call lexical")

    monkeypatch.setattr(
        "engine.rag.enterprise_product_runtime.load_enterprise_profile_runtime",
        forbidden_lexical,
    )
    config = EnterpriseProductRuntimeConfig(
        profile_root=Path("profiles"),
        profile_identity="profile-v1",
        dashscope_api_key="key",
    )
    with pytest.raises(RetrievalAdapterError) as error:
        load_enterprise_product_runtime(config=config)
    assert error.value.reason_code == "enterprise_rag_not_configured"
    assert lexical_calls == 0


def test_explicit_lexical_is_available_only_when_selected(monkeypatch) -> None:
    runtime = _FakeRuntime()
    monkeypatch.setattr(
        "engine.rag.enterprise_product_runtime.load_enterprise_profile_runtime",
        lambda **_kwargs: runtime,
    )
    product = load_enterprise_product_runtime(
        config=EnterpriseProductRuntimeConfig(
            retrieval_mode="lexical",
            profile_root=Path("profiles"),
            profile_identity="profile-v1",
        )
    )
    assert product.identity.retrieval_mode == "lexical"
    assert product.identity.semantic_identity is None
    product.close()
    product.close()
    assert runtime.close_calls == 1


def test_semantic_resolver_projects_complete_snapshot_and_never_discovers_backend(monkeypatch) -> None:
    manifest = _semantic_manifest()
    runtime = _FakeRuntime(adapter="knowledge-enterprise-milvus-semantic-v1")
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        "engine.rag.enterprise_product_runtime.load_enterprise_semantic_manifest",
        lambda **_kwargs: manifest,
    )

    def fake_load(**kwargs):
        observed.update(kwargs)
        return runtime

    monkeypatch.setattr(
        "engine.rag.enterprise_product_runtime.load_enterprise_semantic_runtime",
        fake_load,
    )
    provider = SimpleNamespace(model=manifest.embedding_model, dimensions=manifest.embedding_dimensions)
    product = load_enterprise_product_runtime(
        config=EnterpriseProductRuntimeConfig(
            profile_root=Path("profiles"),
            profile_identity="profile-v1",
            semantic_root=Path("semantic"),
            semantic_identity="semantic-v1",
            dashscope_api_key="key",
        ),
        query_provider_factory=lambda received: provider if received is manifest else pytest.fail(),  # type: ignore[return-value]
    )
    identity = product.identity.safe_projection()
    assert identity["retrieval_mode"] == "semantic"
    assert identity["semantic_manifest_identity"] == "manifest-v1"
    assert identity["milvus_collection"] == "enterprise_collection_v1"
    assert identity["unit_set_identity"] == "unit-set-v1"
    assert observed["query_provider"] is provider
    assert observed["allow_cross_thread"] is False

    # API/Trace 使用 safe_projection；Eval 只能把同一个 resolver identity 投影到 artifact，
    # 不能重新猜测 model、collection 或 unit-set。
    resolved = build_external_resolved_runtime(
        product_identity=product.identity,
        bundle=SimpleNamespace(
            release_identity="profile-v1",
            corpus_identity="corpus-v1",
            authorization_policy_identity="authorization-v1",
            outbound_policy_identity="release-outbound-v1",
        ),
        composer=SimpleNamespace(identity="composer-v1"),
        model="qwen3.7-plus",
        timeout_seconds=60.0,
    )
    assert resolved.retrieval_mode == identity["retrieval_mode"]
    assert resolved.semantic_identity == identity["semantic_identity"]
    assert resolved.semantic_manifest_identity == identity["semantic_manifest_identity"]
    assert resolved.embedding_model == identity["embedding_model"]
    assert resolved.milvus_collection == identity["milvus_collection"]
    assert resolved.unit_set_identity == identity["unit_set_identity"]


def test_unknown_retrieval_mode_is_rejected_closed_world() -> None:
    with pytest.raises(RetrievalAdapterError) as error:
        EnterpriseProductRuntimeConfig(retrieval_mode="auto").validate()
    assert error.value.reason_code == "enterprise_rag_mode_invalid"


class _FakeMilvusClient:
    """记录冷启动顺序，确保单测不需要真实 Docker/Milvus。"""

    latest: "_FakeMilvusClient | None" = None
    load_state = "Loaded"
    description = "enterprise-semantic-identity:semantic-v1"

    def __init__(self, **_kwargs) -> None:
        type(self).latest = self
        self.events: list[str] = []
        self.close_calls = 0

    def load_collection(self, *, collection_name: str) -> None:
        del collection_name
        self.events.append("load")

    def has_collection(self, *, collection_name: str) -> bool:
        del collection_name
        self.events.append("exists")
        return True

    def describe_collection(self, *, collection_name: str):
        del collection_name
        self.events.append("identity")
        return {"description": type(self).description}

    def get_load_state(self, **_kwargs):
        self.events.append("state")
        return {"state": type(self).load_state}

    def close(self) -> None:
        self.close_calls += 1


def _install_fake_pymilvus(monkeypatch) -> None:
    module = ModuleType("pymilvus")
    module.MilvusClient = _FakeMilvusClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pymilvus", module)


def test_semantic_runtime_loads_collection_before_unit_set_check_and_closes_once(monkeypatch) -> None:
    _install_fake_pymilvus(monkeypatch)
    _FakeMilvusClient.load_state = "Loaded"
    _FakeMilvusClient.description = "enterprise-semantic-identity:semantic-v1"

    def fake_unit_set(client, _collection_name):
        client.events.append("unit-set")
        return 139214, "unit-set-v1"

    monkeypatch.setattr("engine.rag.enterprise_semantic._milvus_unit_set", fake_unit_set)
    adapter = EnterpriseMilvusSemanticAdapter(
        manifest=_semantic_manifest(), provider=SimpleNamespace()
    )
    client = _FakeMilvusClient.latest
    assert client is not None
    assert client.events == ["exists", "identity", "load", "state", "unit-set"]
    adapter.close()
    adapter.close()
    assert client.close_calls == 1


def test_semantic_runtime_fails_closed_before_query_when_collection_is_not_loaded(monkeypatch) -> None:
    _install_fake_pymilvus(monkeypatch)
    _FakeMilvusClient.load_state = "NotLoad"
    _FakeMilvusClient.description = "enterprise-semantic-identity:semantic-v1"
    monkeypatch.setattr(
        "engine.rag.enterprise_semantic._milvus_unit_set",
        lambda *_args: pytest.fail("unit-set query must wait for loaded readiness"),
    )
    with pytest.raises(RetrievalAdapterError) as error:
        EnterpriseMilvusSemanticAdapter(
            manifest=_semantic_manifest(), provider=SimpleNamespace()
        )
    client = _FakeMilvusClient.latest
    assert error.value.reason_code == "semantic_collection_not_loaded"
    assert client is not None
    assert client.events == ["exists", "identity", "load", "state"]
    assert client.close_calls == 1


def test_semantic_runtime_rejects_collection_identity_before_loading(monkeypatch) -> None:
    _install_fake_pymilvus(monkeypatch)
    _FakeMilvusClient.description = "enterprise-semantic-identity:another-candidate"
    with pytest.raises(RetrievalAdapterError) as error:
        EnterpriseMilvusSemanticAdapter(
            manifest=_semantic_manifest(), provider=SimpleNamespace()
        )
    client = _FakeMilvusClient.latest
    assert error.value.reason_code == "semantic_collection_identity_mismatch"
    assert client is not None
    assert client.events == ["exists", "identity"]
    assert client.close_calls == 1


def test_semantic_runtime_rejects_profile_snapshot_drift_and_closes_profile(monkeypatch) -> None:
    manifest = _semantic_manifest()
    runtime = SimpleNamespace(
        bundle=SimpleNamespace(
            corpus_identity="different-corpus",
            unit_recipe_identity="unit-recipe-v1",
        ),
        close_calls=0,
    )

    def close() -> None:
        runtime.close_calls += 1

    runtime.close = close
    monkeypatch.setattr(
        "engine.rag.enterprise_semantic.load_enterprise_semantic_manifest",
        lambda **_kwargs: manifest,
    )
    monkeypatch.setattr(
        "engine.rag.enterprise_runtime.load_enterprise_profile_runtime",
        lambda **_kwargs: runtime,
    )
    monkeypatch.setattr(
        "engine.rag.enterprise_semantic.EnterpriseMilvusSemanticAdapter",
        lambda **_kwargs: pytest.fail("drift must fail before Milvus adapter construction"),
    )
    with pytest.raises(RetrievalAdapterError) as error:
        load_enterprise_semantic_runtime(
            profile_root=Path("profiles"),
            profile_identity="profile-v1",
            semantic_root=Path("semantic"),
            semantic_identity="semantic-v1",
            query_provider=SimpleNamespace(
                model=manifest.embedding_model,
                dimensions=manifest.embedding_dimensions,
            ),
        )
    assert error.value.reason_code == "semantic_profile_snapshot_mismatch"
    assert runtime.close_calls == 1
