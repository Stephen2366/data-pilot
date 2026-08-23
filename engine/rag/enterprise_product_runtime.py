"""M44A：统一解析并持有 EnterpriseRAG-Bench 产品检索 runtime。

★ 这个 module 是 API 与 Eval 共用的唯一组装入口。它只接受可信启动配置，验证 profile、
semantic manifest、embedding 与 collection 的身份后，才交付现有 ``EnterpriseProfileRuntime``。
HTTP 请求体永远不能在 semantic/lexical 之间切换，也不能指定 collection 或出站权限。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from engine.rag.enterprise_runtime import EnterpriseProfileRuntime, load_enterprise_profile_runtime
from engine.rag.enterprise_semantic import (
    KNOWLEDGE_EMBEDDING_POLICY,
    EnterpriseSemanticManifest,
    load_enterprise_semantic_manifest,
    load_enterprise_semantic_runtime,
)
from engine.rag.retrieval import RetrievalAdapterError
from engine.schema_retrieval.embedding_provider import DashScopeEmbeddingProvider


EnterpriseRetrievalMode = Literal["semantic", "lexical"]
QueryProviderFactory = Callable[[EnterpriseSemanticManifest], DashScopeEmbeddingProvider]


@dataclass(frozen=True)
class EnterpriseProductRuntimeConfig:
    """可信配置的 typed 快照；空路径/identity 不会被猜测或自动发现。"""

    retrieval_mode: str = "semantic"
    profile_root: Path | None = None
    profile_identity: str = ""
    semantic_root: Path | None = None
    semantic_identity: str = ""
    dashscope_api_key: str = ""
    dashscope_embedding_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    embedding_model: str = "qwen3.7-text-embedding"
    embedding_dimensions: int = 1024
    timeout_seconds: float = 60.0
    allow_cross_thread: bool = False

    @classmethod
    def from_settings(cls, settings: Any, *, allow_cross_thread: bool = True) -> "EnterpriseProductRuntimeConfig":
        """从应用 Settings 建立同一份配置，不在 engine 内直接读取环境变量。"""

        return cls(
            retrieval_mode=settings.enterprise_rag_retrieval_mode,
            profile_root=settings.enterprise_rag_profile_root,
            profile_identity=settings.enterprise_rag_profile_identity,
            semantic_root=settings.enterprise_rag_semantic_root,
            semantic_identity=settings.enterprise_rag_semantic_identity,
            dashscope_api_key=settings.dashscope_api_key,
            dashscope_embedding_base_url=settings.dashscope_embedding_base_url,
            embedding_model=settings.qwen_embedding_model,
            embedding_dimensions=settings.qwen_embedding_dimensions,
            timeout_seconds=settings.llm_timeout_seconds,
            allow_cross_thread=allow_cross_thread,
        )

    def normalized_mode(self) -> EnterpriseRetrievalMode:
        """拒绝未登记 mode；拼写错误不能变成 lexical fallback。"""

        value = self.retrieval_mode.strip().lower()
        if value not in {"semantic", "lexical"}:
            raise RetrievalAdapterError("enterprise_rag_mode_invalid", value or "empty")
        return value  # type: ignore[return-value]

    def validate(self) -> EnterpriseRetrievalMode:
        """在访问 SQLite/Milvus 前闭合必填配置和 semantic provider 身份。"""

        mode = self.normalized_mode()
        if self.profile_root is None or not self.profile_identity.strip():
            raise RetrievalAdapterError(
                "enterprise_rag_not_configured", "profile root/identity are required"
            )
        if mode == "semantic":
            if self.semantic_root is None or not self.semantic_identity.strip():
                raise RetrievalAdapterError(
                    "enterprise_rag_not_configured", "semantic root/identity are required"
                )
            if not self.dashscope_api_key:
                raise RetrievalAdapterError(
                    "enterprise_rag_embedding_not_configured", "DASHSCOPE_API_KEY is required"
                )
        return mode


@dataclass(frozen=True)
class EnterpriseProductRuntimeIdentity:
    """可进入 readiness、Trace 和 Eval 的安全 runtime 身份，不保存本机路径/API key。"""

    retrieval_mode: EnterpriseRetrievalMode
    profile_identity: str
    release_identity: str
    corpus_identity: str
    retrieval_adapter_identity: str
    retrieval_recipe_identity: str
    semantic_identity: str | None = None
    semantic_manifest_identity: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    milvus_collection: str | None = None
    unit_set_identity: str | None = None

    def safe_projection(self) -> dict[str, Any]:
        """返回 closed-world JSON 视图；None 显式表示 lexical 不适用，而不是漏记。"""

        return asdict(self)


class EnterpriseProductRuntime:
    """把已验证 runtime 与其 identity 成对持有，并提供幂等关闭。"""

    def __init__(
        self,
        *,
        runtime: EnterpriseProfileRuntime,
        identity: EnterpriseProductRuntimeIdentity,
    ) -> None:
        self.runtime = runtime
        self.identity = identity
        self._closed = False

    def close(self) -> None:
        """应用 shutdown、Eval context 和初始化异常共用同一释放路径。"""

        if not self._closed:
            self.runtime.close()
            self._closed = True

    def __enter__(self) -> "EnterpriseProductRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _default_query_provider(
    config: EnterpriseProductRuntimeConfig,
    manifest: EnterpriseSemanticManifest,
) -> DashScopeEmbeddingProvider:
    """按 manifest 已冻结的模型/维度创建 query provider，避免文档向量与问题向量漂移。"""

    if (
        config.embedding_model != manifest.embedding_model
        or config.embedding_dimensions != manifest.embedding_dimensions
    ):
        raise RetrievalAdapterError(
            "semantic_query_embedding_mismatch", manifest.semantic_identity
        )
    return DashScopeEmbeddingProvider(
        api_key=config.dashscope_api_key,
        base_url=config.dashscope_embedding_base_url,
        model=config.embedding_model,
        dimensions=config.embedding_dimensions,
        text_type="query",
        outbound_policy=KNOWLEDGE_EMBEDDING_POLICY,
        outbound_node_purpose="knowledge_embedding",
        outbound_data_class="public_benchmark_document",
        timeout=config.timeout_seconds,
    )


def load_enterprise_product_runtime(
    *,
    config: EnterpriseProductRuntimeConfig,
    query_provider_factory: QueryProviderFactory | None = None,
) -> EnterpriseProductRuntime:
    """★ 解析 lexical/semantic 并返回唯一产品 runtime；任何 semantic 失败都直接上抛。

    lexical 分支保留给显式历史复现。semantic 分支不会在异常时进入 lexical，也不会创建、
    reset 或修复 collection；collection 的强校验继续由 M34 adapter 承担。
    """

    mode = config.validate()
    assert config.profile_root is not None  # validate 已闭合，assert 只帮助类型检查器。
    if mode == "lexical":
        runtime = load_enterprise_profile_runtime(
            root=config.profile_root,
            profile_identity=config.profile_identity,
            allow_cross_thread=config.allow_cross_thread,
        )
        identity = EnterpriseProductRuntimeIdentity(
            retrieval_mode=mode,
            profile_identity=runtime.manifest.profile_identity,
            release_identity=runtime.bundle.release_identity,
            corpus_identity=runtime.bundle.corpus_identity,
            retrieval_adapter_identity=runtime.adapter.identity,
            retrieval_recipe_identity=runtime.adapter.recipe_identity,
        )
        return EnterpriseProductRuntime(runtime=runtime, identity=identity)

    assert config.semantic_root is not None
    manifest = load_enterprise_semantic_manifest(
        semantic_root=config.semantic_root,
        semantic_identity=config.semantic_identity,
    )
    provider = (
        query_provider_factory(manifest)
        if query_provider_factory is not None
        else _default_query_provider(config, manifest)
    )
    runtime = load_enterprise_semantic_runtime(
        profile_root=config.profile_root,
        profile_identity=config.profile_identity,
        semantic_root=config.semantic_root,
        semantic_identity=config.semantic_identity,
        query_provider=provider,
        allow_cross_thread=config.allow_cross_thread,
    )
    identity = EnterpriseProductRuntimeIdentity(
        retrieval_mode=mode,
        profile_identity=runtime.manifest.profile_identity,
        release_identity=runtime.bundle.release_identity,
        corpus_identity=runtime.bundle.corpus_identity,
        retrieval_adapter_identity=runtime.adapter.identity,
        retrieval_recipe_identity=runtime.adapter.recipe_identity,
        semantic_identity=manifest.semantic_identity,
        semantic_manifest_identity=manifest.manifest_identity,
        embedding_provider=manifest.embedding_provider,
        embedding_model=manifest.embedding_model,
        embedding_dimensions=manifest.embedding_dimensions,
        milvus_collection=manifest.collection_name,
        unit_set_identity=manifest.unit_set_identity,
    )
    return EnterpriseProductRuntime(runtime=runtime, identity=identity)
