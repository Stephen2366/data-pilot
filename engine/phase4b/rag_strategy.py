"""M46-E：服务端 RAG acquisition strategy 组装边界。

HTTP 请求只会进入既有 ``RAGTool`` interface，不知道 Pipeline/Subgraph 的存在。本模块把
strategy 选择限制在可信的应用配置层，并把两种实现都收敛成 ``DocumentEvidenceAcquirer``。

★ 这层像 Spring 中按 profile 装配 Bean：业务调用方依赖同一个接口，只有启动配置决定注入
哪个实现。它不是运行失败后的自动降级器；需要回退时显式重启为 ``pipeline``，避免一次请求
悄悄跨策略、跨预算执行两遍。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.phase4b.b4_contracts import load_b4_contract_bundle
from engine.phase4b.external_requirement_formation import (
    B4QuestionObligationSupplier,
    ExternalRequirementFormer,
)
from engine.phase4b.rag_diagnostics import ContextExpansionAdapter
from engine.phase4b.rag_recovery_requirement_proposal import B4ProposalTransport
from engine.phase4b.rag_subgraph import (
    BoundedRAGSubgraphAcquirer,
    BusinessT4SlotProvider,
    ExternalFormationSlotProvider,
)
from engine.rag.evidence_acquisition import (
    ActiveLoader,
    DocumentEvidenceAcquirer,
    PipelineEvidenceAcquirer,
)
from engine.rag.knowledge_tool import KnowledgeTool

RAGStrategyName = Literal["pipeline", "subgraph"]
B4_BUNDLE = load_b4_contract_bundle()


class RAGStrategyConfigurationError(ValueError):
    """strategy 或其受信依赖未闭合时，在真正检索前失败。"""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ConfiguredRAGAcquisition:
    """组装结果：内部 adapter 加一份可安全进入 readiness/Trace/Eval 的身份。"""

    strategy: RAGStrategyName
    runtime_scope: Literal["business_release", "external_profile"]
    acquirer: DocumentEvidenceAcquirer

    @property
    def strategy_identity(self) -> str:
        """返回稳定策略身份，避免只凭可变配置字符串对账。"""

        return f"phase4b-rag-acquisition-strategy:{self.strategy}:v1"

    def safe_projection(self) -> dict[str, str]:
        """输出可进入 readiness/Trace 的白名单组装事实。"""

        return {
            "strategy": self.strategy,
            "strategy_identity": self.strategy_identity,
            "runtime_scope": self.runtime_scope,
            "acquirer_identity": str(getattr(self.acquirer, "identity", "unidentified")),
            "contract_identity": B4_BUNDLE.content_identity,
        }


def _validate_strategy(strategy: str) -> RAGStrategyName:
    """按 B4 闭集合同校验并规范化 acquisition strategy。"""

    value = strategy.strip().lower()
    if value not in set(B4_BUNDLE.payload["strategies"]):
        raise RAGStrategyConfigurationError("rag_acquisition_strategy_invalid")
    return value  # type: ignore[return-value]


def configure_business_acquisition(
    *,
    strategy: str,
    knowledge_tool: KnowledgeTool,
    active_loader: ActiveLoader,
) -> ConfiguredRAGAcquisition:
    """组装 business Pipeline 或 T4 Subgraph；business 永不获得 proposal/expansion。"""

    selected = _validate_strategy(strategy)
    pipeline = PipelineEvidenceAcquirer(
        knowledge_tool=knowledge_tool,
        active_loader=active_loader,
    )
    acquirer: DocumentEvidenceAcquirer = pipeline
    if selected == "subgraph":
        acquirer = BoundedRAGSubgraphAcquirer(
            initial_acquirer=pipeline,
            knowledge_tool=knowledge_tool,
            active_loader=active_loader,
            slot_provider=BusinessT4SlotProvider(),
            runtime_scope="business_release",
        )
    return ConfiguredRAGAcquisition(selected, "business_release", acquirer)


def configure_external_acquisition(
    *,
    strategy: str,
    knowledge_tool: KnowledgeTool,
    active_loader: ActiveLoader,
    proposal_transport: B4ProposalTransport | None = None,
    expansion_adapter: ContextExpansionAdapter | None = None,
) -> ConfiguredRAGAcquisition:
    """组装 external strategy；仅 Subgraph 要求 proposal transport 与 authority expansion。"""

    selected = _validate_strategy(strategy)
    pipeline = PipelineEvidenceAcquirer(
        knowledge_tool=knowledge_tool,
        active_loader=active_loader,
    )
    acquirer: DocumentEvidenceAcquirer = pipeline
    if selected == "subgraph":
        if proposal_transport is None or expansion_adapter is None:
            raise RAGStrategyConfigurationError("rag_subgraph_dependencies_unavailable")
        former = ExternalRequirementFormer(
            structured_supplier=B4QuestionObligationSupplier(proposal_transport)
        )
        acquirer = BoundedRAGSubgraphAcquirer(
            initial_acquirer=pipeline,
            knowledge_tool=knowledge_tool,
            active_loader=active_loader,
            slot_provider=ExternalFormationSlotProvider(former),
            runtime_scope="external_profile",
            expansion_adapter=expansion_adapter,
        )
    return ConfiguredRAGAcquisition(selected, "external_profile", acquirer)
