"""M44A FastAPI lifespan、readiness 与普通 RAG fail-closed 接线。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from engine.harness.contracts import HarnessRequest, RouteDecision
from engine.rag.answer_flow import AnswerEvidenceRequirement


class _FixedRAGRouter:
    """测试只固定 route，不替代 RAG Tool 或伪造 Evidence。"""

    def decide(self, request: HarnessRequest) -> RouteDecision:
        del request
        return RouteDecision(
            "rag",
            "test_fixed_rag",
            True,
            "answer",
            requirement=AnswerEvidenceRequirement(),
        )


def _empty_db():
    """RAG 路径不会使用 DB Session；只满足 FastAPI dependency 形状。"""

    yield None


def test_unconfigured_app_keeps_liveness_but_rag_is_unavailable_without_fallback(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, APP_ENV="test", DASHSCOPE_API_KEY="")
    application = create_app(settings)
    application.dependency_overrides[get_db] = _empty_db
    application.state.harness_router = _FixedRAGRouter()
    application.state.trace_path = tmp_path / "trace.jsonl"
    with TestClient(application) as client:
        assert client.get("/health").json() == {"status": "ok"}
        readiness = client.get("/health/rag")
        response = client.post("/api/query", json={"question": "policy?", "user_role": "ops"})

    assert readiness.status_code == 503
    assert readiness.json()["reason_code"] == "enterprise_rag_not_configured"
    body = response.json()
    assert (body["route"], body["execution_status"], body["answer_status"]) == (
        "rag", "external_unavailable", "no_answer"
    )
    assert body["reason_code"] == "enterprise_rag_not_configured"
    assert body["citations"] == [] and body["docs_used"] == []


def test_lifespan_loads_once_reports_safe_identity_and_closes_once(monkeypatch) -> None:
    identity = SimpleNamespace(
        retrieval_mode="semantic",
        retrieval_adapter_identity="knowledge-enterprise-milvus-semantic-v1",
        milvus_collection="collection-v1",
        semantic_identity="semantic-v1",
        safe_projection=lambda: {
            "retrieval_mode": "semantic",
            "profile_identity": "profile-v1",
            "semantic_identity": "semantic-v1",
            "milvus_collection": "collection-v1",
        },
    )

    class FakeProduct:
        def __init__(self) -> None:
            self.identity = identity
            self.runtime = SimpleNamespace()
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    product = FakeProduct()
    calls = 0

    def fake_load(*, config):
        nonlocal calls
        calls += 1
        assert config.retrieval_mode == "semantic"
        return product

    monkeypatch.setattr("app.main.load_enterprise_product_runtime", fake_load)
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        DASHSCOPE_API_KEY="key",
        ENTERPRISE_RAG_PROFILE_ROOT="profiles",
        ENTERPRISE_RAG_PROFILE_IDENTITY="profile-v1",
        ENTERPRISE_RAG_SEMANTIC_ROOT="semantic",
        ENTERPRISE_RAG_SEMANTIC_IDENTITY="semantic-v1",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        readiness = client.get("/health/rag")
        assert readiness.status_code == 200
        assert readiness.json()["runtime_identity"]["milvus_collection"] == "collection-v1"
        assert calls == 1
    assert product.close_calls == 1
    assert application.state.rag_tool_factory is None
