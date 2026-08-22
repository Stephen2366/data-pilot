"""M41 产品 RAG E2E seam：真实经过 API/Harness，且每题只执行一次。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.main import app
from engine.rag.answer_flow import ClaimDraft, GenerationContext
from eval.rag_e2e_contracts import RAGScenario, load_rag_catalog
from eval.rag_e2e_generation import BusinessEvalEvidenceComposer, RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, RAGProductExecutor
from eval.rag_e2e_scoring import project_gate, score_execution


CATALOG = Path("eval/cases/rag/scenarios.yaml")


class RecordingComposer:
    """模拟真实 provider 的结构化返回，同时保留 attempt/usage telemetry。"""

    identity = "m41-recording-composer-v1"

    def __init__(self) -> None:
        self.attempts: list[dict[str, object]] = []
        self._calls = 0

    def usage_projection(self) -> dict[str, int]:
        return {"requests": self._calls, "input_tokens": self._calls * 10, "completion_tokens": self._calls * 5, "total_tokens": self._calls * 15}

    def compose(
        self,
        *,
        context: GenerationContext,
        question: str,
        confirmed_conditions: tuple[str, ...],
        max_claims: int,
    ) -> tuple[ClaimDraft, ...]:
        self._calls += 1
        self.attempts.append({"status": "success", "request": self._calls})
        return tuple(
            ClaimDraft(
                text=item.payload.content,
                support_text=item.payload.content,
                evidence_id=item.ref.evidence_id,
                anchor=item.ref.anchor,
            )
            for item in context.evidence[:max_claims]
        )


def test_product_executor_runs_router_harness_rag_and_restores_default(tmp_path: Path) -> None:
    catalog = load_rag_catalog(CATALOG)
    scenario = catalog.by_id()["quality_refund_materials"]
    composer = RecordingComposer()
    previous_factory = app.state.rag_tool_factory
    executor = RAGProductExecutor(
        composer=composer,
        runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "traces",
    )

    evidence = executor.execute(scenario=scenario, replicate=1)

    assert (evidence.route, evidence.execution_status, evidence.answer_status, evidence.safety_status) == (
        "rag", "completed", "complete", "passed"
    )
    assert evidence.graph_steps == ("route", "rag_tool", "controller")
    assert evidence.graph_invocation_count == evidence.rag_tool_calls == 1
    assert "refund_policy_quality" in dict(evidence.stage_document_keys)["cited"]
    assert evidence.provider_usage["requests"] == 1
    assert len(evidence.provider_attempts) == 1
    assert evidence.response_trace_consistent is True
    assert app.state.rag_tool_factory is previous_factory


def test_no_candidate_is_observed_without_calling_composer(tmp_path: Path) -> None:
    catalog = load_rag_catalog(CATALOG)
    scenario = catalog.by_id()["unsupported_warranty_rule"]
    composer = RecordingComposer()
    executor = RAGProductExecutor(
        composer=composer,
        runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "traces",
    )

    evidence = executor.execute(scenario=scenario, replicate=1)

    assert (evidence.route, evidence.execution_status, evidence.answer_status, evidence.safety_status) == (
        "rag", "completed", "insufficient_evidence", "passed"
    )
    assert evidence.reason_code == "evidence_no_candidate"
    assert evidence.answer == "当前无法形成可公开的答案。"
    assert evidence.provider_attempts == ()
    assert evidence.provider_usage.get("requests", 0) == 0


def test_eval_only_business_outbound_guard_allows_policy_docs_and_denies_security_docs(tmp_path: Path) -> None:
    catalog = load_rag_catalog(CATALOG)
    allowed_composer = BusinessEvalEvidenceComposer(RecordingComposer())
    executor = RAGProductExecutor(
        composer=allowed_composer,
        runtime_metadata=ComposerRuntimeMetadata(
            model="fake", generation_outbound_policy_identity=RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY
        ),
        trace_root=tmp_path / "allowed-traces",
    )
    allowed = executor.execute(scenario=catalog.by_id()["quality_refund_materials"], replicate=1)
    assert allowed.reason_code == "answer_completed"
    assert allowed.provider_attempts[0]["authorized_source_data_classes"] == ["role_restricted_policy_text"]

    denied_scenario = RAGScenario(
        scenario_id="security_policy_denied", classification="diagnostic",
        question="敏感数据安全政策规则是什么？", user_role="admin",
        expected_axes=("rag", "failed", "no_answer", "passed"),
        expected_reason="composer_unavailable", expected_document_keys=("sensitive_data_policy",),
        required_answer_terms=(), forbidden_public_terms=(),
        required_assertions=("route_correct",), advisory_assertions=(),
    )
    denied_composer = BusinessEvalEvidenceComposer(RecordingComposer())
    denied_executor = RAGProductExecutor(
        composer=denied_composer,
        runtime_metadata=ComposerRuntimeMetadata(
            model="fake", generation_outbound_policy_identity=RAG_EVAL_BUSINESS_OUTBOUND_IDENTITY
        ),
        trace_root=tmp_path / "denied-traces",
    )
    denied = denied_executor.execute(scenario=denied_scenario, replicate=1)
    assert (denied.execution_status, denied.reason_code) == ("failed", "composer_unavailable")
    assert denied.provider_attempts[0]["error_subtype"] == "eval_outbound_data_class_denied"


def test_external_unavailable_is_inconclusive_but_observed_bad_schema_fails(tmp_path: Path) -> None:
    scenario = load_rag_catalog(CATALOG).by_id()["quality_refund_materials"]
    executor = RAGProductExecutor(
        composer=RecordingComposer(), runtime_metadata=ComposerRuntimeMetadata(model="fake"),
        trace_root=tmp_path / "traces",
    )
    success = executor.execute(scenario=scenario, replicate=1)
    common = {
        "execution_status": "failed", "answer_status": "no_answer",
        "reason_code": "composer_unavailable", "answer": None, "citations": (), "docs_used": (),
        "stage_document_keys": tuple(
            (stage, () if stage == "cited" else keys) for stage, keys in success.stage_document_keys
        ),
        "stage_counts": tuple(
            (stage, 0 if stage == "cited" else count) for stage, count in success.stage_counts
        ),
    }
    unavailable = replace(success, **common, provider_attempts=({"status": "failed", "error_subtype": "timeout"},))
    unavailable_results = score_execution(scenario, unavailable)
    assert project_gate(unavailable_results).status == "inconclusive"
    assert any(item.assertion_id == "answer_present" and item.status == "not_observed" for item in unavailable_results)

    invalid = replace(
        success, **common,
        provider_attempts=({"status": "failed", "error_subtype": "composer_response_invalid_json"},),
    )
    assert project_gate(score_execution(scenario, invalid)).status == "failed"
