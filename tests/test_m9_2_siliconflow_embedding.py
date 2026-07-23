"""M9.2 SiliconFlow embedding provider 测试。

真实 API 调用放在 smoke 脚本里；单元测试只用 fake transport 验证请求、解析和 batch 行为，
避免默认 pytest 消耗 API 额度或依赖网络。
"""

from __future__ import annotations

from engine.schema_retrieval.embedding_provider import SiliconFlowEmbeddingProvider


def test_siliconflow_embedding_provider_sends_batch_request_and_parses_vectors() -> None:
    """provider 应按 SiliconFlow embeddings 契约发送 batch，并按 index 还原向量顺序。"""

    calls: list[dict[str, object]] = []

    def fake_post_json(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return {
            "object": "list",
            "model": payload["model"],
            "data": [
                {"object": "embedding", "embedding": [0.1, 0.2, 0.3], "index": 1},
                {"object": "embedding", "embedding": [0.4, 0.5, 0.6], "index": 0},
            ],
            "usage": {"total_tokens": 12},
        }

    provider = SiliconFlowEmbeddingProvider(
        api_key="test-key",
        base_url="https://api.siliconflow.cn/v1",
        model="BAAI/bge-m3",
        post_json=fake_post_json,
    )

    vectors = provider.embed_texts(["第一个文本", "第二个文本"])

    assert vectors == [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]
    assert provider.embed("单条文本") == [0.4, 0.5, 0.6]
    assert calls[0]["url"] == "https://api.siliconflow.cn/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["payload"]["model"] == "BAAI/bge-m3"
    assert calls[0]["payload"]["encoding_format"] == "float"


def test_siliconflow_embedding_provider_accepts_qwen_dimensions() -> None:
    """Qwen3 embedding 支持 dimensions 参数，provider 需要透传。"""

    captured_payloads: list[dict[str, object]] = []

    def fake_post_json(_url: str, _headers: dict[str, str], payload: dict[str, object], _timeout: float) -> dict[str, object]:
        captured_payloads.append(payload)
        return {"data": [{"embedding": [0.1, 0.2], "index": 0}]}

    provider = SiliconFlowEmbeddingProvider(
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-0.6B",
        dimensions=1024,
        post_json=fake_post_json,
    )

    provider.embed("渠道 GMV")

    assert captured_payloads[0]["dimensions"] == 1024
