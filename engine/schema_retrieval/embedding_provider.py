"""真实 embedding provider 实验实现。

M9.2 先接 SiliconFlow 的 OpenAI-like embeddings API，用于验证“真实中文 embedding + Milvus”
是否比 M9 的 deterministic fake embedding 更适合 Schema Retrieval。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib import request

from engine.governance import OutboundRequest, require_outbound

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_DASHSCOPE_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
DEFAULT_QWEN_EMBEDDING_MODEL = "qwen3.7-text-embedding"

PostJson = Callable[[str, dict[str, str], dict[str, object], float], dict[str, object]]


def _post_json(url: str, headers: dict[str, str], payload: dict[str, object], timeout: float) -> dict[str, object]:
    """用标准库发送 JSON POST，避免为了实验额外引入 requests 依赖。"""

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class SiliconFlowEmbeddingProvider:
    """SiliconFlow embeddings provider。

    ★ 默认模型选 `BAAI/bge-m3`：它是中文 / 多语言 RAG 场景里常见的稳妥选择；如果后续想试
    Qwen3 embedding，可通过 `model` 与 `dimensions` 显式切换。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_SILICONFLOW_BASE_URL,
        model: str = DEFAULT_SILICONFLOW_EMBEDDING_MODEL,
        dimensions: int | None = None,
        timeout: float = 30.0,
        post_json: PostJson = _post_json,
    ) -> None:
        """保存 API 配置；不在初始化时发请求，方便测试和配置检查。"""

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout = timeout
        self._post_json = post_json
        self._cache: dict[str, list[float]] = {}

    def embed(self, text: str) -> list[float]:
        """生成单条文本向量。"""

        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量，并按输入顺序返回。"""

        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError("SILICONFLOW_API_KEY is required for SiliconFlowEmbeddingProvider.")

        missing_texts = [text for text in texts if text not in self._cache]
        if not missing_texts:
            return [self._cache[text] for text in texts]

        # ★ 网络前强制出站门：只放行已登记的 schema_text 数据类别；缺策略或字段越界在
        # transport 前失败关闭，同 provider 的新 Knowledge payload 也无法绕过。
        require_outbound(
            OutboundRequest(
                receiver="siliconflow_embedding",
                node_purpose="schema_embedding",
                data_class="schema_text",
                fields=frozenset({"texts", "model", "dimensions"}),
                fallback_available=False,
            )
        )
        payload: dict[str, object] = {
            "model": self.model,
            "input": missing_texts,
            "encoding_format": "float",
        }
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        response = self._post_json(
            f"{self.base_url}/embeddings",
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            payload,
            self.timeout,
        )

        data = response.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"SiliconFlow embeddings response missing data: {response}")
        vectors_by_index: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            index = int(item.get("index", len(vectors_by_index)))
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError(f"SiliconFlow embedding item missing vector: {item}")
            vectors_by_index[index] = [float(value) for value in embedding]
        for index, text in enumerate(missing_texts):
            self._cache[text] = vectors_by_index[index]
        return [self._cache[text] for text in texts]


class DashScopeEmbeddingProvider:
    """DashScope / Qwen 文本向量 provider。

    ★ 第一轮实验只把 dense embedding 接入现有 Milvus FLOAT_VECTOR；`qwen3.7-text-embedding`
    的 sparse / instruct 能力先不混入 A/B，避免分不清收益来自模型还是检索策略变化。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_DASHSCOPE_EMBEDDING_BASE_URL,
        model: str = DEFAULT_QWEN_EMBEDDING_MODEL,
        dimensions: int = 1024,
        text_type: str = "document",
        output_type: str = "dense",
        max_batch_size: int = 20,
        timeout: float = 30.0,
        post_json: PostJson = _post_json,
    ) -> None:
        """保存 DashScope embedding 配置；初始化不发请求，便于单测和配置检查。"""

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.text_type = text_type
        self.output_type = output_type
        self.max_batch_size = max_batch_size
        self.timeout = timeout
        self._post_json = post_json
        self._cache: dict[str, list[float]] = {}

    def embed(self, text: str) -> list[float]:
        """生成单条文本向量。"""

        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量，并按输入顺序返回 dense vectors。"""

        if not texts:
            return []
        if not self.api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is required for DashScopeEmbeddingProvider.")

        missing_texts = [text for text in texts if text not in self._cache]
        if not missing_texts:
            return [self._cache[text] for text in texts]

        # ★ 同 SiliconFlow 路径：真实网络前必须经过出站裁决，失败关闭且不影响已缓存结果。
        require_outbound(
            OutboundRequest(
                receiver="dashscope_embedding",
                node_purpose="schema_embedding",
                data_class="schema_text",
                fields=frozenset({"texts", "model", "dimensions"}),
                fallback_available=False,
            )
        )
        for batch_start in range(0, len(missing_texts), self.max_batch_size):
            batch_texts = missing_texts[batch_start : batch_start + self.max_batch_size]
            payload: dict[str, object] = {
                "model": self.model,
                "input": {"texts": batch_texts},
                "parameters": {
                    "dimension": self.dimensions,
                    "text_type": self.text_type,
                    "output_type": self.output_type,
                },
            }
            response = self._post_json(
                f"{self.base_url}/services/embeddings/text-embedding/text-embedding",
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                payload,
                self.timeout,
            )

            output = response.get("output")
            if not isinstance(output, dict):
                raise RuntimeError(f"DashScope embeddings response missing output: {response}")
            embeddings = output.get("embeddings")
            if not isinstance(embeddings, list):
                raise RuntimeError(f"DashScope embeddings response missing embeddings: {response}")

            vectors_by_index: dict[int, list[float]] = {}
            for item in embeddings:
                if not isinstance(item, dict):
                    continue
                index = int(item.get("text_index", len(vectors_by_index)))
                embedding = item.get("embedding")
                if not isinstance(embedding, list):
                    raise RuntimeError(f"DashScope embedding item missing dense vector: {item}")
                vectors_by_index[index] = [float(value) for value in embedding]

            for index, text in enumerate(batch_texts):
                self._cache[text] = vectors_by_index[index]
        return [self._cache[text] for text in texts]
