"""真实 embedding provider 实验实现。

M9.2 先接 SiliconFlow 的 OpenAI-like embeddings API，用于验证“真实中文 embedding + Milvus”
是否比 M9 的 deterministic fake embedding 更适合 Schema Retrieval。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib import request

DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"

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
