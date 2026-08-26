"""M46-F：Formal Eval 必须保存 child timeline 与完整性明确的分项 usage。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from engine.rag.answer_flow import ClaimDraft, GenerationContext, RAGAnswerFlow
from engine.rag.evidence_acquisition import PipelineEvidenceAcquirer
from engine.rag.knowledge_tool import KnowledgeTool
from engine.rag.release import load_active_release
from eval.rag_e2e_contracts import load_rag_catalog
from eval.rag_e2e_runtime import ComposerRuntimeMetadata, RAGProductExecutor
from eval.rag_b4_projection import project_b4_eval_diagnostics
from scripts.run_m46_historical_paired import _aggregate_b4_usage, _migrate_launch_failure


def _child() -> dict[str, object]:
    return {
        "attempts": [{
            "ordinal": 1,
            "action": "context_expansion_candidate",
            "status": "completed",
            "eligible_actions": ["context_expansion_candidate", "stop"],
            "rejected_actions": ["query_rewrite_candidate"],
            "evidence_added": 2,
            "duplicate_count": 0,
            "consumption": {"expansion_evidence_added": 2},
            "progress_reason": "evidence_gain",
            "question": "private",
        }],
        "consumption": {
            "initial_retrieval_batches": 1,
            "rewrite_retrieval_batches": 1,
            "expansion_candidates_scanned": 2,
            "expansion_evidence_added": 2,
            "candidates_examined": 10,
            "unique_merged_evidence": 5,
            "selected": 3,
            "generation_visible": 3,
            "proposal_calls": 1,
            "model_calls": 1,
            "total_tokens": 321,
            "token_usage_observed": True,
            "retrieval_attempts_observed": True,
            "latency_ms": 12.5,
            "raw_response": "private",
        },
        "termination": "answer_ready",
        "detail_code": "required_coverage_complete",
        "admission_decision": "structured_question_obligations",
        "admission_reason_code": "eligible",
        "formed_requirements": [{
            "slot_signature": "sha256-safe",
            "focused_query_fingerprint": "sha256-safe",
            "support_group_count": 2,
            "supplier_identity": "fixture",
            "formation_reason_category": "requested_fact",
            "allowed_recovery_actions": ["query_rewrite_candidate"],
            "coverage_semantics": "single_authorized_document_all_groups_v1",
            "focused_query": "private",
        }],
        "prompt": "private",
    }


def test_subgraph_projection_is_same_source_private_free_and_usage_complete() -> None:
    child = _child()
    diagnostics, usage = project_b4_eval_diagnostics(
        runtime_family="phase4b-b4-external-product-harness:subgraph:v1",
        rag_diagnostics={"knowledge_tool_calls": 1},
        result_evidence_validity={"subgraph": child},
        trace_evidence_validity={"subgraph": child},
        composer_usage={"request_count": 1, "total_tokens": 200},
    )

    projection = diagnostics["b4_acquisition"]
    assert projection["projection_status"] == "observed"
    assert projection["source_consistent"] is True
    assert projection["provider_usage"] == {
        "composer_requests": 1,
        "composer_total_tokens": 200,
        "formation_requests": 1,
        "formation_total_tokens": 321,
        "retrieval_requests_known": 2,
        "provider_requests_known_total": 4,
        "provider_tokens_known_total": 521,
        "retrieval_attempts_observed": True,
        "formation_token_usage_observed": True,
        "all_provider_token_usage_observed": False,
    }
    serialized = str(projection).casefold()
    assert "private" not in serialized
    assert usage["b4_provider_requests_known_total"] == 4
    assert usage["b4_provider_tokens_known_total"] == 521


def test_pipeline_projection_counts_one_retrieval_without_child_ledger() -> None:
    diagnostics, usage = project_b4_eval_diagnostics(
        runtime_family="phase4b-b4-external-product-harness:pipeline:v1",
        rag_diagnostics={"knowledge_tool_calls": 1},
        result_evidence_validity={},
        trace_evidence_validity={},
        composer_usage={"requests": 1, "total_tokens": 100},
    )

    projection = diagnostics["b4_acquisition"]
    assert projection["projection_status"] == "not_applicable"
    assert projection["child_ledger"] is None
    assert projection["provider_usage"]["provider_requests_known_total"] == 2
    assert usage["b4_formation_requests"] == 0


def test_subgraph_single_source_is_not_misreported_as_consistent() -> None:
    diagnostics, _usage = project_b4_eval_diagnostics(
        runtime_family="phase4b-b4-external-product-harness:subgraph:v1",
        rag_diagnostics={"knowledge_tool_calls": 1},
        result_evidence_validity={"subgraph": _child()},
        trace_evidence_validity={},
        composer_usage={},
    )

    assert diagnostics["b4_acquisition"]["projection_status"] == "partial_observed"
    assert diagnostics["b4_acquisition"]["source_consistent"] is False


def test_legacy_m41_projection_is_byte_shape_compatible() -> None:
    diagnostics, usage = project_b4_eval_diagnostics(
        runtime_family="phase4-rag-external-product-harness-fixed-route-v1",
        rag_diagnostics={"knowledge_tool_calls": 1},
        result_evidence_validity={"subgraph": _child()},
        trace_evidence_validity={"subgraph": _child()},
        composer_usage={"requests": 1, "total_tokens": 100},
    )

    assert diagnostics == {"knowledge_tool_calls": 1}
    assert usage == {"requests": 1, "total_tokens": 100}


def test_paired_usage_summary_preserves_request_and_token_completeness() -> None:
    diagnostics, _usage = project_b4_eval_diagnostics(
        runtime_family="phase4b-b4-external-product-harness:subgraph:v1",
        rag_diagnostics={"knowledge_tool_calls": 1},
        result_evidence_validity={"subgraph": _child()},
        trace_evidence_validity={"subgraph": _child()},
        composer_usage={"request_count": 1, "total_tokens": 200},
    )
    summary = _aggregate_b4_usage({"executions": [{"rag_diagnostics": diagnostics}]})

    assert summary["provider_requests_known_total"] == 4
    assert summary["provider_tokens_known_total"] == 521
    assert summary["request_count_complete"] is True
    assert summary["token_count_complete"] is False
    assert summary["source_consistent"] is True


def test_resume_manifest_moves_stale_failure_into_launch_lineage() -> None:
    migrated = _migrate_launch_failure({
        "status": "inconclusive",
        "completed_arms": [],
        "failed_arm": "pipeline",
        "failed_exit_code": 1,
    })

    assert "failed_arm" not in migrated and "failed_exit_code" not in migrated
    assert migrated["launch_history"] == [{
        "status": "failed", "arm": "pipeline", "exit_code": 1,
    }]


def test_product_executor_projects_same_b4_child_into_checkpoint_evidence(tmp_path: Path) -> None:
    """真实 API/Trace seam 的 result 与 JSONL child 必须对账后进入 execution artifact。"""

    class _Composer:
        identity = "m46-eval-projection-composer"

        def __init__(self) -> None:
            self.request_count = 0
            self.total_tokens = 0
            self.attempts: list[dict[str, object]] = []

        def usage_projection(self) -> dict[str, int]:
            return {"request_count": self.request_count, "total_tokens": self.total_tokens}

        def compose(
            self, *, context: GenerationContext, question: str,
            confirmed_conditions: tuple[str, ...], max_claims: int,
        ) -> tuple[ClaimDraft, ...]:
            del question, confirmed_conditions
            self.request_count += 1
            self.total_tokens += 10
            self.attempts.append({"status": "success"})
            return tuple(ClaimDraft(
                text=item.payload.content,
                support_text=item.payload.content,
                evidence_id=item.ref.evidence_id,
                anchor=item.ref.anchor,
            ) for item in context.evidence[:max_claims])

    class _B4FixtureAcquirer:
        identity = "phase4b-bounded-rag-subgraph-acquisition-v1"

        def __init__(self) -> None:
            self._pipeline = PipelineEvidenceAcquirer(
                knowledge_tool=KnowledgeTool(), active_loader=load_active_release,
            )

        def acquire(self, *, request, started_at):
            result = self._pipeline.acquire(request=request, started_at=started_at)
            return replace(result, evidence_validity={
                **result.evidence_validity,
                "subgraph": _child(),
            }, strategy_identity=self.identity)

    catalog = load_rag_catalog(Path("eval/cases/rag/scenarios.yaml"))
    scenario = catalog.by_id()["quality_refund_materials"]
    composer = _Composer()
    metadata = ComposerRuntimeMetadata(model="fixture")
    baseline = RAGProductExecutor(
        composer=composer,
        runtime_metadata=metadata,
        trace_root=tmp_path / "baseline",
    ).resolved_runtime()
    executor = RAGProductExecutor(
        composer=composer,
        runtime_metadata=metadata,
        trace_root=tmp_path / "traces",
        answer_flow_factory=lambda: RAGAnswerFlow(
            composer=composer,
            evidence_acquirer=_B4FixtureAcquirer(),
        ),
        resolved_runtime_override=replace(
            baseline,
            runtime_family="phase4b-b4-external-product-harness:subgraph:v1",
        ),
    )

    evidence = executor.execute(scenario=scenario, replicate=1)

    projection = evidence.rag_diagnostics["b4_acquisition"]
    assert projection["projection_status"] == "observed"
    assert projection["source_consistent"] is True
    assert projection["child_ledger"]["termination"] == "answer_ready"
    assert evidence.provider_usage["b4_provider_requests_known_total"] == 4

    class _InvalidComposer(_Composer):
        """模拟真实 run 中 provider 返回后 support 合同失败的三题。"""

        def compose(
            self, *, context: GenerationContext, question: str,
            confirmed_conditions: tuple[str, ...], max_claims: int,
        ) -> tuple[ClaimDraft, ...]:
            del question, confirmed_conditions, max_claims
            self.request_count += 1
            self.total_tokens += 10
            self.attempts.append({"status": "success"})
            item = context.evidence[0]
            return (ClaimDraft(
                text="unsupported",
                support_text="not in evidence",
                evidence_id=item.ref.evidence_id,
                anchor=item.ref.anchor,
            ),)

    invalid_composer = _InvalidComposer()
    invalid_executor = RAGProductExecutor(
        composer=invalid_composer,
        runtime_metadata=metadata,
        trace_root=tmp_path / "invalid-traces",
        answer_flow_factory=lambda: RAGAnswerFlow(
            composer=invalid_composer,
            evidence_acquirer=_B4FixtureAcquirer(),
        ),
        resolved_runtime_override=replace(
            baseline,
            runtime_family="phase4b-b4-external-product-harness:subgraph:v1",
        ),
    )
    invalid = invalid_executor.execute(scenario=scenario, replicate=1)

    assert invalid.reason_code == "composer_output_invalid"
    assert invalid.rag_diagnostics["b4_acquisition"]["projection_status"] == "observed"
    assert invalid.rag_diagnostics["b4_acquisition"]["source_consistent"] is True
