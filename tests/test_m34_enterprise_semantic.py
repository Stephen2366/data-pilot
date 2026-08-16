"""M34 semantic 长运行恢复与出站边界的本地测试。"""

from __future__ import annotations

from urllib.error import URLError

import pytest

from engine.governance import GovernanceError
from engine.rag.enterprise_semantic import KNOWLEDGE_EMBEDDING_POLICY, _embed_with_retry
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider


def test_knowledge_embedding_policy_allows_exact_fields_and_cache_can_be_released() -> None:
    calls = 0

    def fake_post(_url, _headers, payload, _timeout):
        nonlocal calls
        calls += 1
        return {"output": {"embeddings": [{"embedding": [1.0, 0.0], "text_index": 0}]}}

    provider = DashScopeEmbeddingProvider(
        api_key="key",
        post_json=fake_post,
        outbound_policy=KNOWLEDGE_EMBEDDING_POLICY,
        outbound_node_purpose="knowledge_embedding",
        outbound_data_class="public_benchmark_document",
    )
    assert provider.embed("public synthetic text") == [1.0, 0.0]
    provider.clear_cache()
    assert provider.embed("public synthetic text") == [1.0, 0.0]
    assert calls == 2


def test_default_policy_still_denies_new_knowledge_embedding_before_transport() -> None:
    provider = DashScopeEmbeddingProvider(
        api_key="key",
        outbound_node_purpose="knowledge_embedding",
        outbound_data_class="public_benchmark_document",
        post_json=lambda *_: pytest.fail("transport must not be called"),
    )
    with pytest.raises(GovernanceError):
        provider.embed("denied")


def test_transient_embedding_failure_retries_but_contract_error_does_not(monkeypatch) -> None:
    class TransientProvider:
        calls = 0

        def embed_texts(self, _texts):
            self.calls += 1
            if self.calls == 1:
                raise URLError("temporary")
            return [[0.1]]

        def clear_cache(self):
            pass

    monkeypatch.setattr("engine.rag.enterprise_semantic.sleep", lambda _seconds: None)
    transient = TransientProvider()
    assert _embed_with_retry(transient, ["text"]) == [[0.1]]  # type: ignore[arg-type]
    assert transient.calls == 2

    class InvalidProvider(TransientProvider):
        def embed_texts(self, _texts):
            raise RuntimeError("invalid response")

    with pytest.raises(RuntimeError):
        _embed_with_retry(InvalidProvider(), ["text"])  # type: ignore[arg-type]
