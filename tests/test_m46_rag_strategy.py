"""M46-E：服务端 strategy registry 保持 Pipeline baseline 与 Subgraph experimental 隔离。"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import create_app
from engine.phase4b.rag_strategy import (
    RAGStrategyConfigurationError,
    configure_business_acquisition,
    configure_external_acquisition,
)
from engine.phase4b.rag_subgraph import BoundedRAGSubgraphAcquirer
from engine.rag.evidence_acquisition import PipelineEvidenceAcquirer
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release


class _ProposalTransport:
    model = "fixture"
    request_count = 0
    total_tokens = 0

    def complete(self, **_: object) -> str:
        return '{"obligations":[]}'


class _ExpansionAdapter:
    identity = "fixture-expansion-v1"


def test_pipeline_is_default_and_explicit_baseline_for_both_scopes() -> None:
    settings = Settings(_env_file=None)
    app = create_app(settings)
    assert settings.phase4b_rag_strategy == "pipeline"
    assert app.state.b4_task_enabled is False

    tool = KnowledgeTool()
    business = configure_business_acquisition(
        strategy="pipeline", knowledge_tool=tool, active_loader=load_active_release
    )
    external = configure_external_acquisition(
        strategy="pipeline", knowledge_tool=tool, active_loader=load_active_release
    )
    assert isinstance(business.acquirer, PipelineEvidenceAcquirer)
    assert isinstance(external.acquirer, PipelineEvidenceAcquirer)
    assert business.safe_projection()["strategy"] == "pipeline"


def test_server_subgraph_strategy_wires_business_and_external_without_client_field() -> None:
    settings = Settings(_env_file=None, PHASE4B_RAG_STRATEGY="subgraph")
    app = create_app(settings)
    assert app.state.b4_task_enabled is True
    assert "phase4b_rag_strategy" not in app.openapi()["components"]["schemas"]["QueryRequest"]["properties"]

    tool = KnowledgeTool()
    business = configure_business_acquisition(
        strategy="subgraph", knowledge_tool=tool, active_loader=load_active_release
    )
    external = configure_external_acquisition(
        strategy="subgraph",
        knowledge_tool=tool,
        active_loader=load_active_release,
        proposal_transport=_ProposalTransport(),
        expansion_adapter=_ExpansionAdapter(),  # type: ignore[arg-type] - 只验证 trusted assembly。
    )
    assert isinstance(business.acquirer, BoundedRAGSubgraphAcquirer)
    assert isinstance(external.acquirer, BoundedRAGSubgraphAcquirer)
    assert external.safe_projection()["runtime_scope"] == "external_profile"


def test_subgraph_missing_dependencies_and_unknown_strategy_fail_closed() -> None:
    tool = KnowledgeTool()
    with pytest.raises(RAGStrategyConfigurationError, match="rag_subgraph_dependencies_unavailable"):
        configure_external_acquisition(
            strategy="subgraph", knowledge_tool=tool, active_loader=load_active_release
        )
    with pytest.raises(RAGStrategyConfigurationError, match="rag_acquisition_strategy_invalid"):
        configure_business_acquisition(
            strategy="automatic", knowledge_tool=tool, active_loader=load_active_release
        )
