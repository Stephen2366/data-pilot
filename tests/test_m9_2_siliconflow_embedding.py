"""M9.2 SiliconFlow embedding provider 测试。

真实 API 调用放在 smoke 脚本里；单元测试只用 fake transport 验证请求、解析和 batch 行为，
避免默认 pytest 消耗 API 额度或依赖网络。
"""

from __future__ import annotations

from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider, SiliconFlowEmbeddingProvider


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


def test_dashscope_embedding_provider_sends_text_embedding_request_and_parses_vectors() -> None:
    """Qwen embedding 应走 DashScope 文本向量契约，并只把 dense vector 交给现有 Milvus。"""

    calls: list[dict[str, object]] = []

    def fake_post_json(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout})
        return {
            "output": {
                "embeddings": [
                    {"embedding": [0.1, 0.2, 0.3], "text_index": 1},
                    {"embedding": [0.4, 0.5, 0.6], "text_index": 0},
                ]
            },
            "usage": {"total_tokens": 10},
        }

    provider = DashScopeEmbeddingProvider(
        api_key="dashscope-key",
        base_url="https://dashscope.aliyuncs.com/api/v1",
        model="qwen3.7-text-embedding",
        dimensions=1024,
        text_type="document",
        output_type="dense",
        post_json=fake_post_json,
    )

    vectors = provider.embed_texts(["订单金额", "渠道 GMV"])

    assert vectors == [[0.4, 0.5, 0.6], [0.1, 0.2, 0.3]]
    assert calls[0]["url"] == "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
    assert calls[0]["headers"]["Authorization"] == "Bearer dashscope-key"
    assert calls[0]["payload"]["model"] == "qwen3.7-text-embedding"
    assert calls[0]["payload"]["input"] == {"texts": ["订单金额", "渠道 GMV"]}
    assert calls[0]["payload"]["parameters"]["dimension"] == 1024
    assert calls[0]["payload"]["parameters"]["text_type"] == "document"
    assert calls[0]["payload"]["parameters"]["output_type"] == "dense"


def test_dashscope_embedding_provider_batches_large_schema_document_sets() -> None:
    """DashScope embedding 有 batch size 上限，Schema 文档入库时必须自动拆批。"""

    batch_sizes: list[int] = []

    def fake_post_json(_url: str, _headers: dict[str, str], payload: dict[str, object], _timeout: float) -> dict[str, object]:
        texts = payload["input"]["texts"]
        batch_sizes.append(len(texts))
        return {
            "output": {
                "embeddings": [
                    {"embedding": [float(index), 0.0], "text_index": index}
                    for index, _text in enumerate(texts)
                ]
            }
        }

    provider = DashScopeEmbeddingProvider(
        api_key="dashscope-key",
        model="qwen3.7-text-embedding",
        max_batch_size=20,
        post_json=fake_post_json,
    )

    vectors = provider.embed_texts([f"schema doc {index}" for index in range(45)])

    assert batch_sizes == [20, 20, 5]
    assert len(vectors) == 45
